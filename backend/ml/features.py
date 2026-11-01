"""Per-pixel feature extraction shared by training and inference.

Input: RGB uint8/float array (H, W, 3) in 0..255 true-colour.
Output: (H*W, F) float32 feature matrix. Features are deliberately scale/stretch
robust (chromaticity ratios, normalised differences, relative brightness and
multi-scale texture) so a model trained on Sentinel-2 chips transfers to JPEG
uploads.
"""

import numpy as np

FEATURE_NAMES = [
    "r", "g", "b", "gray", "rel_gray",
    "r_chroma", "g_chroma", "b_chroma",
    "sat", "hue_sin", "hue_cos",
    "ndgr", "ndbr", "ndbg",
    "std5", "std15", "std31",
    "mean15_rel", "mean31_rel",
    "ndgr_m15", "ndbr_m15", "sat_m15",
]


def box(a: np.ndarray, k: int) -> np.ndarray:
    pad = k // 2
    p = np.pad(a, pad, mode="reflect")
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def local_std(a: np.ndarray, k: int) -> np.ndarray:
    m = box(a, k)
    return np.sqrt(np.maximum(box(a * a, k) - m * m, 0))


def features(rgb: np.ndarray) -> np.ndarray:
    x = rgb.astype(np.float32) / 255.0
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    eps = 1e-4
    s = r + g + b + eps
    gray = (r + g + b) / 3
    med = float(np.median(gray)) + eps
    mx = x.max(-1)
    mn = x.min(-1)
    sat = (mx - mn) / (mx + eps)
    # hue angle
    hue = np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)
    ndgr = (g - r) / (g + r + eps)
    ndbr = (b - r) / (b + r + eps)
    ndbg = (b - g) / (b + g + eps)
    feats = [
        r, g, b, gray, gray / med,
        r / s, g / s, b / s,
        sat, np.sin(hue), np.cos(hue),
        ndgr, ndbr, ndbg,
        local_std(gray, 5), local_std(gray, 15), local_std(gray, 31),
        box(gray, 15) / med, box(gray, 31) / med,
        box(ndgr, 15), box(ndbr, 15), box(sat, 15),
    ]
    return np.stack([f.reshape(-1) for f in feats], axis=1).astype(np.float32)