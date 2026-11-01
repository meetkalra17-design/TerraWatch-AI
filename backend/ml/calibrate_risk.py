"""Historical risk-score calibration for Punjab districts.

1. Pulls ERA5 daily precipitation + Tmax (Open-Meteo archive, 1995-2025) for every
   district centroid and GloFAS daily river discharge (Open-Meteo flood API, 2000-2025)
   for every river gauge cell.
2. Writes climate normals used at runtime (data/punjab_climate.json):
   monthly precipitation totals (SPI drought modelling), Tmax day-of-year normals
   (IMD heatwave departures) and discharge day-of-year normals per gauge.
3. Builds daily monsoon-season (Jun-Oct, 2015-2025) features per district and labels
   them with the documented flood events in lib/punjab.FLOOD_EVENTS.
4. Fits a logistic-regression risk model; evaluates it event-by-event (train on the
   other years, test on the held-out event year) -> ml/artifacts/risk_calibration.json

Run: cd /app/backend && python -m ml.calibrate_risk
"""

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from backend.lib.punjab import DATA, FLOOD_EVENTS, STATIONS, districts

ART = Path(__file__).parent / "artifacts"
CACHE = DATA / "punjab_hist"
FEATURES = ["log_rain3", "log_rain7", "log_rain30", "log_q_ratio", "log_q_ratio_max3"]
WEATHER_VARIABLES = (
    "precipitation_sum,temperature_2m_max"
)


def get(url: str, params: dict) -> dict:
    for attempt in range(6):
        try:
            r = httpx.get(url, params=params, timeout=120)
            if r.status_code == 429:
                time.sleep(30 * (attempt + 1)); continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"failed {url}")


def fetch_history() -> tuple[dict, dict]:
    CACHE.mkdir(exist_ok=True)
    clim: dict = {}
    for d in districts():
        f = CACHE / f"wx_{d['slug']}.json"
        cached = json.loads(f.read_text()) if f.exists() else None
        if cached is None or any(variable not in cached for variable in WEATHER_VARIABLES.split(",")):
            js = get("https://archive-api.open-meteo.com/v1/archive", {
                "latitude": d["lat"], "longitude": d["lng"], "start_date": "1995-01-01", "end_date": "2025-10-25",
                "daily": WEATHER_VARIABLES, "timezone": "Asia/Kolkata",
            })
            f.write_text(json.dumps(js["daily"]))
            print("wx", d["name"]); time.sleep(1)
        clim[d["name"]] = json.loads(f.read_text())
    q: dict = {}
    for sid, s in STATIONS.items():
        f = CACHE / f"q_{sid}.json"
        if not f.exists():
            js = get("https://flood-api.open-meteo.com/v1/flood", {
                "latitude": s["lat"], "longitude": s["lng"], "start_date": "2000-01-01", "end_date": "2025-10-25",
                "daily": "river_discharge",
            })
            f.write_text(json.dumps(js["daily"]))
            print("q", sid); time.sleep(1)
        q[sid] = json.loads(f.read_text())
    return clim, q


def doy_normal(dates: list[str], vals: np.ndarray, start: str, end: str, smooth: int = 15) -> list[float]:
    """Day-of-year mean over [start,end] smoothed with a circular window."""
    doy = np.array([date.fromisoformat(x).timetuple().tm_yday for x in dates]) - 1
    m = np.array([start <= x <= end for x in dates]) & ~np.isnan(vals)
    sums = np.bincount(doy[m], weights=vals[m], minlength=366)
    cnt = np.bincount(doy[m], minlength=366)
    raw = sums / np.maximum(cnt, 1)
    k = np.ones(smooth) / smooth
    ext = np.concatenate([raw[-smooth:], raw, raw[:smooth]])
    return [round(float(x), 2) for x in np.convolve(ext, k, mode="same")[smooth:-smooth]]


def nanarr(x: list) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in x], dtype=float)


def rolling_sum(a: np.ndarray, k: int) -> np.ndarray:
    a = np.nan_to_num(a)
    c = np.concatenate([[0], np.cumsum(a)])
    out = np.zeros_like(a)
    out[k - 1:] = c[k:] - c[:-k]
    out[: k - 1] = c[1:k]
    return out


def main() -> None:
    ART.mkdir(exist_ok=True)
    wx, q = fetch_history()

    climate = {"generated_at": datetime.now(timezone.utc).isoformat(), "districts": {}, "stations": {}}
    for name, d in wx.items():
        dates = d["time"]
        p = nanarr(d["precipitation_sum"])
        months: dict[str, float] = {}
        for t, v in zip(dates, p):
            if not np.isnan(v):
                months[t[:7]] = months.get(t[:7], 0.0) + float(v)
        climate["districts"][name] = {
            "monthly_precip": {k: round(v, 1) for k, v in months.items()},
            "tmax_normal": doy_normal(dates, nanarr(d["temperature_2m_max"]), "1995-01-01", "2024-12-31"),
        }
    for sid, d in q.items():
        climate["stations"][sid] = {"q_normal": doy_normal(d["time"], nanarr(d["river_discharge"]), "2000-01-01", "2024-12-31")}
    (DATA / "punjab_climate.json").write_text(json.dumps(climate, separators=(",", ":")))
    print("climate normals written")

    rows, labels, years, meta = [], [], [], []
    for dist in districts():
        name = dist["name"]
        d = wx[name]
        dates = d["time"]
        p = nanarr(d["precipitation_sum"])
        r3, r7, r30 = rolling_sum(p, 3), rolling_sum(p, 7), rolling_sum(p, 30)
        sq = q[dist["station"]]
        qmap = dict(zip(sq["time"], nanarr(sq["river_discharge"])))
        qn = climate["stations"][dist["station"]]["q_normal"]
        ratio = np.array([
            (qmap.get(t, np.nan) / max(qn[date.fromisoformat(t).timetuple().tm_yday - 1], 1.0)) for t in dates
        ])
        ratio = np.nan_to_num(ratio, nan=1.0)
        rmax3 = np.maximum.reduce([ratio, np.roll(ratio, 1), np.roll(ratio, 2)])
        for i, t in enumerate(dates):
            if t < "2015-01-01" or int(t[5:7]) not in (6, 7, 8, 9, 10):
                continue
            lab = any(e["start"] <= t <= e["end"] and name in e["districts"] for e in FLOOD_EVENTS)
            rows.append([np.log1p(r3[i]), np.log1p(r7[i]), np.log1p(r30[i]), np.log(max(ratio[i], 0.05)), np.log(max(rmax3[i], 0.05))])
            labels.append(int(lab)); years.append(int(t[:4])); meta.append((name, t))
    X = np.array(rows); y = np.array(labels); yr = np.array(years)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Xs = (X - mu) / sd
    print(f"samples={len(y)} positives={int(y.sum())}")

    def fit(mask):
        return LogisticRegression(C=0.5, max_iter=2000).fit(Xs[mask], y[mask])

    held = []
    for e in FLOOD_EVENTS:
        ey = int(e["start"][:4])
        m = fit(yr != ey)
        test = yr == ey
        pr = m.predict_proba(Xs[test])[:, 1]
        yt = y[test]
        names = [meta[i] for i in np.flatnonzero(test)]
        hits = {n for (n, t), pp in zip(names, pr) if e["start"] <= t <= e["end"] and pp >= 0.25}
        nonevent = pr[yt == 0]
        held.append({
            "event": e["name"], "event_id": e["id"], "test_year": ey,
            "auc": round(float(roc_auc_score(yt, pr)), 4), "brier": round(float(brier_score_loss(yt, pr)), 4),
            "districts_affected": len(e["districts"]),
            "districts_flagged_high": len(hits & set(e["districts"])),
            "hit_rate": round(len(hits & set(e["districts"])) / len(e["districts"]), 3),
            "false_alarm_rate": round(float((nonevent >= 0.25).mean()), 4),
        })
        print(held[-1])

    final = fit(np.ones_like(y, dtype=bool))
    pall = final.predict_proba(Xs)[:, 1]
    calib = {
        "version": "tw-risk-lr-" + datetime.now(timezone.utc).strftime("%Y%m%d"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "features": FEATURES, "mean": mu.round(5).tolist(), "std": sd.round(5).tolist(),
        "coef": final.coef_[0].round(5).tolist(), "intercept": round(float(final.intercept_[0]), 5),
        "thresholds": {"critical": 0.5, "high": 0.25, "moderate": 0.1},
        "samples": int(len(y)), "positives": int(y.sum()), "period": "2015-2025 Jun-Oct, 22 districts",
        "in_sample": {"auc": round(float(roc_auc_score(y, pall)), 4), "brier": round(float(brier_score_loss(y, pall)), 4)},
        "held_out_events": held,
        "events": FLOOD_EVENTS,
    }
    (ART / "risk_calibration.json").write_text(json.dumps(calib, indent=2))
    print("calibration written", calib["in_sample"])


if __name__ == "__main__":
    main()