"""Train and evaluate a time-aware XGBoost flood-risk model for Punjab.

The training data is downloaded by the existing calibration pipeline:
- Open-Meteo historical daily precipitation and temperature.
- Open-Meteo/GloFAS historical daily river discharge.
- Documented Punjab flood events used as district-day labels.

The split is chronological by event year. This prevents future weather values
from leaking into the held-out evaluation. Accuracy is reported alongside
balanced accuracy, ROC-AUC, average precision, Brier score, and event hit rate.
The model must not be used as a sole dispatch decision.
"""

import json
import csv
import re
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier

from backend.lib.punjab import DATA, FLOOD_EVENTS, districts
from backend.ml.calibrate_risk import fetch_history, nanarr, rolling_sum

ART = Path(__file__).parent / "artifacts"
FEATURES = [
    "log_rain1",
    "log_rain3",
    "log_rain7",
    "log_rain30",
    "temp_mean7",
    "rain_days7",
    "rain_peak3",
    "discharge_change3",
    "discharge_max7",
    "log_q_ratio",
    "log_q_ratio_max3",
    "month_sin",
    "month_cos",
]


def normalize_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip().lower())
    return value.replace("district", "").strip()


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if np.isnan(values).all():
        raise ValueError("Historical weather series contains no usable values")
    fill = float(np.nanmedian(values))
    return rolling_sum(np.nan_to_num(values, nan=fill), window) / window


def require_series(weather: dict, key: str) -> np.ndarray:
    if key not in weather:
        raise ValueError(f"Historical weather cache is missing required series: {key}")
    return nanarr(weather[key])


def load_inventory_events() -> list[dict]:
    path = DATA / "IndiaFloodInventory.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing downloaded flood inventory: {path}")
    events: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            start = row.get("Start Date", "").split(" ")[0]
            end = row.get("End Date", "").split(" ")[0]
            if not start or not end:
                continue
            try:
                start_date = datetime.strptime(start, "%d/%m/%y").date()
                end_date = datetime.strptime(end, "%d/%m/%y").date()
            except ValueError:
                continue
            if end_date < date(1995, 1, 1):
                continue
            districts_text = row.get("Districts", "") or ""
            states_text = row.get("State", "") or ""
            district_names = {normalize_name(item) for item in districts_text.split(",") if item.strip()}
            if "punjab" in states_text.lower() and not district_names:
                district_names = {normalize_name(district["name"]) for district in districts()}
            events.append({
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "districts": district_names,
                "source": "IFI-Impacts",
            })
    return events


def historical_priors(events: list[dict], district: str, timestamp: date) -> tuple[float, float, float]:
    name = normalize_name(district)
    past = [event for event in events if name in event["districts"] and event["end"] < timestamp.isoformat()]
    days = sum((date.fromisoformat(event["end"]) - date.fromisoformat(event["start"])).days + 1 for event in past)
    recent_start = timestamp.replace(year=timestamp.year - 3)
    recent = sum(date.fromisoformat(event["start"]) >= recent_start for event in past)
    return float(min(len(past), 50)), float(min(days, 365)), float(min(recent, 10))


def build_rows(
    wx: dict,
    q: dict,
    inventory_events: list[dict],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[tuple[str, str]], dict[int, set[str]]]:
    rows: list[list[float]] = []
    labels: list[int] = []
    years: list[int] = []
    meta: list[tuple[str, str]] = []
    event_districts: dict[int, set[str]] = {}
    for district in districts():
        name = district["name"]
        weather = wx[name]
        dates = weather["time"]
        precipitation = require_series(weather, "precipitation_sum")
        rain1 = np.nan_to_num(precipitation, nan=0.0)
        rain3, rain7, rain30 = rolling_sum(rain1, 3), rolling_sum(rain1, 7), rolling_sum(rain1, 30)
        tmax = require_series(weather, "temperature_2m_max")
        temp_mean7 = rolling_mean(tmax, 7)
        rain_days7 = rolling_sum((rain1 >= 1.0).astype(float), 7)
        rain_peak3 = np.maximum.reduce([rain1, np.roll(rain1, 1), np.roll(rain1, 2)])
        station = q[district["station"]]
        discharge = dict(zip(station["time"], nanarr(station["river_discharge"])))
        # A local rolling quantile avoids depending on a second calibration artifact.
        q_values = np.array([discharge.get(t, np.nan) for t in dates], dtype=float)
        q_values = np.nan_to_num(q_values, nan=0.0)
        q_normal = max(float(np.nanmedian(q_values)), 1.0)
        ratio = np.maximum(q_values / q_normal, 0.05)
        ratio_max3 = np.maximum.reduce([ratio, np.roll(ratio, 1), np.roll(ratio, 2)])
        for i, timestamp in enumerate(dates):
            if timestamp < "2015-01-01" or int(timestamp[5:7]) not in (6, 7, 8, 9, 10):
                continue
            month = int(timestamp[5:7])
            label = any(
                event["start"] <= timestamp <= event["end"] and name in event["districts"]
                for event in FLOOD_EVENTS
            )
            normalized = normalize_name(name)
            label = label or any(
                event["start"] <= timestamp <= event["end"] and normalized in event["districts"]
                for event in inventory_events
            )
            if label:
                event_districts.setdefault(int(timestamp[:4]), set()).add(name)
            discharge_change3 = max(ratio[i] - ratio[max(0, i - 3)], 0.0)
            discharge_max7 = float(np.max(ratio[max(0, i - 6):i + 1]))
            rows.append([
                np.log1p(rain1[i]),
                np.log1p(rain3[i]),
                np.log1p(rain7[i]),
                np.log1p(rain30[i]),
                temp_mean7[i],
                rain_days7[i],
                np.log1p(rain_peak3[i]),
                discharge_change3,
                np.log(discharge_max7),
                np.log(ratio[i]),
                np.log(ratio_max3[i]),
                np.sin(2 * np.pi * month / 12),
                np.cos(2 * np.pi * month / 12),
            ])
            labels.append(int(label))
            years.append(int(timestamp[:4]))
            meta.append((name, timestamp))
    return np.asarray(rows, dtype=np.float32), np.asarray(labels, dtype=np.int8), np.asarray(years), meta, event_districts


def metrics(y_true: np.ndarray, probability: np.ndarray, threshold: float = 0.25) -> dict[str, float]:
    predicted = probability >= threshold
    return {
        "threshold": threshold,
        "accuracy": round(float(accuracy_score(y_true, predicted)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, predicted)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, probability)), 4),
        "average_precision": round(float(average_precision_score(y_true, probability)), 4),
        "precision": round(float(precision_score(y_true, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, predicted, zero_division=0)), 4),
        "brier": round(float(brier_score_loss(y_true, probability)), 4),
    }


def make_model() -> XGBClassifier:
    return XGBClassifier(
        n_estimators=220,
        max_depth=4,
        learning_rate=0.045,
        subsample=0.85,
        colsample_bytree=0.9,
        min_child_weight=5,
        reg_lambda=2.0,
        scale_pos_weight=3.0,
        objective="binary:logistic",
        eval_metric="logloss",
        tree_method="hist",
        random_state=42,
        n_jobs=1,
    )


def main() -> None:
    ART.mkdir(exist_ok=True)
    print("Downloading/reusing historical weather and river data...")
    wx, q = fetch_history()
    inventory_events = load_inventory_events()
    X, y, years, meta, event_districts = build_rows(wx, q, inventory_events)
    print(f"samples={len(y)} positives={int(y.sum())} positive_rate={float(y.mean()):.4f}")

    held_out: list[dict] = []
    event_years = sorted(event_districts)
    for year in event_years:
        train_mask = years != year
        test_mask = years == year
        model = make_model().fit(X[train_mask], y[train_mask])
        probability = model.predict_proba(X[test_mask])[:, 1]
        hit_pairs = [(district_name, score) for (district_name, _), score in zip(np.asarray(meta)[test_mask], probability) if score >= 0.25]
        predicted_districts = {name for name, _ in hit_pairs}
        hit_rate = len(predicted_districts & event_districts[year]) / len(event_districts[year])
        result = {
            "test_year": year,
            "positive_districts": len(event_districts[year]),
            "event_hit_rate": round(hit_rate, 4),
            **metrics(y[test_mask], probability),
        }
        held_out.append(result)
        print(result)

    final = make_model().fit(X, y)
    artifact = ART / "flood_risk_xgboost.json"
    final.save_model(str(artifact.with_suffix(".json")))
    report = {
        "model_version": "tw-flood-xgb-" + datetime.now(timezone.utc).strftime("%Y%m%d"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "XGBClassifier",
        "class_weighting": "scale_pos_weight=3.0",
        "features": FEATURES,
        "data_sources": [
            "Open-Meteo historical weather API",
            "Open-Meteo Flood API (GloFAS river discharge)",
            "India Flood Inventory-Impacts (IFI-Impacts), Zenodo 11069835",
            "Documented Punjab flood events in backend/lib/punjab.py",
        ],
        "scope": "Punjab district-day weather/discharge risk, 1995-2025",
        "geographic_coverage": {
            "weather_and_discharge_features": "Punjab districts only",
            "inventory_label_source": "India-wide",
            "india_wide_weather_model": False,
        },
        "samples": int(len(y)),
        "positive_samples": int(y.sum()),
        "evaluation": "chronological event-year holdout",
        "held_out_events": held_out,
        "inventory_events": len(inventory_events),
        "warning": "Metrics are retrospective and not a guarantee of future flood prediction accuracy. Labels inherit the limitations of a multi-source inventory. Confirm with live gauges, forecasts, satellite observations, and official authorities.",
    }
    (ART / "flood_risk_xgboost_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"saved model={artifact.with_suffix('.json')}")
    print(f"saved metrics={ART / 'flood_risk_xgboost_metrics.json'}")


if __name__ == "__main__":
    main()
