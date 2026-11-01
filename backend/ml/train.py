"""Trains the TerraWatch water-segmentation model.

Data
- Sen1Floods11 v1.1 HandLabeled split (all 446 Sentinel-2 chips, 11 flood events,
  expert hand labels) -> /root/sen1floods11/{S2Hand,LabelHand}
- Punjab-specific weakly labelled Sentinel-2 L2A chips -> /root/punjab_s2 (see build_punjab_dataset.py)

Model: HistGradientBoosting pixel classifier over RGB-derived features (ml/features.py),
so it runs on any true-colour upload.

Evaluation: leave-one-event-out — for each of the 12 events (11 Sen1Floods11 + Punjab)
a model is trained on the other events and scored on the held-out one (IoU/F1/precision/
recall on all labelled pixels). The baseline heuristic engine is scored the same way.

Run: cd /app/backend && python -m ml.train
Outputs: ml/artifacts/flood_model.joblib, ml/artifacts/metrics.json
"""

import glob
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import tifffile
from sklearn.ensemble import HistGradientBoostingClassifier

from backend.ml.features import FEATURE_NAMES, features

S1F = Path("/root/sen1floods11")
PUNJAB = Path("/root/punjab_s2")
ART = Path(__file__).parent / "artifacts"
RNG = np.random.default_rng(7)
SAMPLES_PER_CHIP = 2500
EVAL_PER_CHIP = 6000


def s2_to_rgb(a: np.ndarray) -> np.ndarray:
    # S2Hand band order B1..B12 incl. B8A/B10 -> B4=3, B3=2, B2=1
    rgb = np.stack([a[3], a[2], a[1]], -1).astype(np.float32)
    return np.clip(rgb * 255 / 3000, 0, 255).astype(np.uint8)


def augment(rgb: np.ndarray) -> np.ndarray:
    gain = RNG.uniform(0.7, 1.45)
    gamma = RNG.uniform(0.8, 1.25)
    x = np.clip((rgb.astype(np.float32) / 255) * gain, 0, 1) ** gamma
    return (x * 255).astype(np.uint8)


def load_chips():
    chips = []  # (event, rgb, label)
    for f in sorted(glob.glob(str(S1F / "S2Hand" / "*.tif"))):
        lab = tifffile.imread(f.replace("S2Hand", "LabelHand"))
        chips.append((Path(f).name.split("_")[0], s2_to_rgb(tifffile.imread(f)), lab.astype(np.int8)))
    for f in sorted(glob.glob(str(PUNJAB / "*.npz"))):
        z = np.load(f)
        chips.append(("Punjab", z["rgb"], z["label"].astype(np.int8)))
    return chips


def sample(feat: np.ndarray, lab: np.ndarray, n: int):
    lab = lab.reshape(-1)
    idx = np.flatnonzero(lab >= 0)
    if idx.size == 0:
        return None
    water = idx[lab[idx] == 1]
    dry = idx[lab[idx] == 0]
    take_w = min(water.size, n // 2)
    take_d = min(dry.size, n - take_w)
    sel = np.concatenate([
        RNG.choice(water, take_w, replace=False) if take_w else np.empty(0, int),
        RNG.choice(dry, take_d, replace=False) if take_d else np.empty(0, int),
    ])
    return feat[sel], lab[sel]


def heuristic_pred(rgb: np.ndarray) -> np.ndarray:
    from backend.lib.flood_engine import _water_like
    return _water_like(rgb.astype(np.float32)).reshape(-1)


def scores(tp: int, fp: int, fn: int, tn: int) -> dict:
    iou = tp / max(tp + fp + fn, 1)
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    acc = (tp + tn) / max(tp + fp + fn + tn, 1)
    return {"iou": round(iou, 4), "f1": round(f1, 4), "precision": round(prec, 4), "recall": round(rec, 4), "accuracy": round(acc, 4)}


def make_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=220, learning_rate=0.08, max_leaf_nodes=63, l2_regularization=1.0, random_state=0)


def main() -> None:
    t0 = time.time()
    ART.mkdir(exist_ok=True)
    chips = load_chips()
    events = sorted({c[0] for c in chips})
    print(f"loaded {len(chips)} chips, events={events}")

    train_X: dict[str, list] = {e: [] for e in events}
    train_y: dict[str, list] = {e: [] for e in events}
    eval_X: dict[str, list] = {e: [] for e in events}
    eval_y: dict[str, list] = {e: [] for e in events}
    heur = {e: [0, 0, 0, 0] for e in events}
    labelled = {e: [0, 0] for e in events}  # pixels, water pixels

    for ev, rgb, lab in chips:
        # training samples from 2 augmented copies + original
        for k in range(2):
            img = rgb if k == 0 else augment(rgb)
            s = sample(features(img), lab, SAMPLES_PER_CHIP)
            if s:
                train_X[ev].append(s[0])
                train_y[ev].append(s[1])
        feat = features(rgb)
        flat = lab.reshape(-1)
        idx = np.flatnonzero(flat >= 0)
        if idx.size:
            sel = RNG.choice(idx, min(EVAL_PER_CHIP, idx.size), replace=False)
            eval_X[ev].append(feat[sel])
            eval_y[ev].append(flat[sel])
            hp = heuristic_pred(rgb)[idx]
            gt = flat[idx] == 1
            heur[ev][0] += int((hp & gt).sum()); heur[ev][1] += int((hp & ~gt).sum())
            heur[ev][2] += int((~hp & gt).sum()); heur[ev][3] += int((~hp & ~gt).sum())
            labelled[ev][0] += int(idx.size); labelled[ev][1] += int(gt.sum())
    print(f"features ready in {time.time() - t0:.0f}s")

    per_event = []
    tot = np.zeros(4, dtype=np.int64)
    htot = np.zeros(4, dtype=np.int64)
    for ev in events:
        Xtr = np.concatenate([x for e in events if e != ev for x in train_X[e]])
        ytr = np.concatenate([y for e in events if e != ev for y in train_y[e]])
        m = make_model().fit(Xtr, ytr)
        Xe = np.concatenate(eval_X[ev]); ye = np.concatenate(eval_y[ev]) == 1
        p = m.predict_proba(Xe)[:, 1] > 0.5
        c = np.array([(p & ye).sum(), (p & ~ye).sum(), (~p & ye).sum(), (~p & ~ye).sum()])
        tot += c
        htot += np.array(heur[ev])
        row = {
            "event": ev, "chips": sum(1 for x in chips if x[0] == ev),
            "water_fraction": round(labelled[ev][1] / max(labelled[ev][0], 1), 4),
            "model": scores(*map(int, c)), "baseline": scores(*heur[ev]),
        }
        per_event.append(row)
        print(f"held-out {ev:10s} IoU={row['model']['iou']:.3f} (baseline {row['baseline']['iou']:.3f})  {time.time() - t0:.0f}s")

    Xall = np.concatenate([x for e in events for x in train_X[e]])
    yall = np.concatenate([y for e in events for y in train_y[e]])
    final = make_model().fit(Xall, yall)
    joblib.dump(final, ART / "flood_model.joblib", compress=3)

    metrics = {
        "model_version": "tw-water-hgb-" + datetime.now(timezone.utc).strftime("%Y%m%d"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "HistGradientBoostingClassifier (220 iters, 63 leaves) on 22 RGB-derived pixel features",
        "features": FEATURE_NAMES,
        "datasets": [
            {"name": "Sen1Floods11 v1.1 — HandLabeled S2 (full split)", "chips": sum(1 for x in chips if x[0] != "Punjab"),
             "events": [e for e in events if e != "Punjab"], "labels": "expert hand-labelled water"},
            {"name": "TerraWatch Punjab S2-L2A (2023 & 2025 floods + dry 2024)", "chips": sum(1 for x in chips if x[0] == "Punjab"),
             "events": ["Punjab"], "labels": "weak: SCL water ∪ MNDWI>0.12, clouds masked"},
        ],
        "train_pixels": int(yall.size),
        "evaluation": "leave-one-event-out",
        "per_event": per_event,
        "overall": {"model": scores(*map(int, tot)), "baseline": scores(*map(int, htot))},
        "training_seconds": round(time.time() - t0, 1),
    }
    (ART / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print("overall", metrics["overall"])


if __name__ == "__main__":
    main()