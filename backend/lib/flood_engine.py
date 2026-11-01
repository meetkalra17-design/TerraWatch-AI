"""Simulated spectral flood-detection engine.

Heuristic pseudo-MNDWI on RGB imagery: a pixel is "water-like" when it is smooth
(low local texture) and either blue-dominant or muddy/dark low-saturation. Flood
pixels are water-like in the AFTER scene, not water-like in the BEFORE scene, and
show a significant colour change between the two.
"""

import math
import random
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

GRID = 384  # analysis resolution


def _load(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data)).convert("RGB")


def _box(a: np.ndarray, k: int = 7) -> np.ndarray:
    """Fast box blur via integral image."""
    pad = k // 2
    p = np.pad(a, pad, mode="edge")
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return s / (k * k)


def _water_like(rgb: np.ndarray) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(-1)
    mn = rgb.min(-1)
    v = mx / 255.0
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    gray = rgb.mean(-1)
    std = np.sqrt(np.maximum(_box(gray**2) - _box(gray) ** 2, 0))
    smooth = std < 14
    bluish = (b >= r - 4) & (b >= g - 18) & (v < 0.85)
    muddy = (r >= g - 6) & (g >= b) & (sat < 0.42) & (v > 0.22) & (v < 0.82) & (np.abs(r - g) < 40)
    dark = (v < 0.28) & (sat < 0.5)
    return smooth & (bluish | muddy | dark)


def _clean(mask: np.ndarray) -> np.ndarray:
    img = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))
    return np.array(img) > 127


def analyze(before: bytes, after: bytes, mask_path: Path) -> dict:
    b_img = _load(before)
    a_img = _load(after)
    out_size = a_img.size
    b = np.asarray(b_img.resize((GRID, GRID)), dtype=np.float32)
    a = np.asarray(a_img.resize((GRID, GRID)), dtype=np.float32)

    wb = _clean(_water_like(b))
    wa = _clean(_water_like(a))
    diff = np.sqrt(((a - b) ** 2).sum(-1))
    changed = _box(diff, 5) > 32
    flood = _clean(wa & ~wb & changed)

    total = flood.size
    flooded_pct = float(flood.sum() / total * 100)
    water_before = float(wb.sum() / total * 100)
    water_after = float((wa | flood).sum() / total * 100)
    change_pct = float(changed.sum() / total * 100)

    # cyan RGBA overlay at the after-image resolution
    rgba = np.zeros((GRID, GRID, 4), dtype=np.uint8)
    rgba[flood] = (0, 229, 255, 170)
    Image.fromarray(rgba, "RGBA").resize(out_size, Image.NEAREST).save(mask_path, "PNG")

    # confidence: crisper masks (less speckle) → higher confidence
    edge_ratio = float(np.abs(np.diff(flood.astype(np.int8), axis=1)).sum() / max(flood.sum(), 1))
    confidence = round(max(72.0, min(98.5, 97.0 - edge_ratio * 18)), 1)

    return {
        "flooded_pct": round(flooded_pct, 2),
        "water_before_pct": round(water_before, 2),
        "water_after_pct": round(water_after, 2),
        "change_pct": round(change_pct, 2),
        "confidence": confidence,
    }


def severity_for(pct: float) -> str:
    if pct >= 30:
        return "critical"
    if pct >= 18:
        return "high"
    if pct >= 8:
        return "moderate"
    return "low"


def flood_polygon(lat: float, lng: float, area_km2: float, seed: str) -> list[list[float]]:
    """Irregular polygon (lat/lng ring) whose area roughly matches the flooded area."""
    rnd = random.Random(seed)
    radius_km = max(math.sqrt(max(area_km2, 0.2) / math.pi), 0.4)
    pts: list[list[float]] = []
    n = 18
    for i in range(n):
        ang = 2 * math.pi * i / n
        r = radius_km * rnd.uniform(0.65, 1.35)
        dlat = (r * math.sin(ang)) / 110.574
        dlng = (r * math.cos(ang)) / (111.320 * math.cos(math.radians(lat)))
        pts.append([round(lat + dlat, 5), round(lng + dlng, 5)])
    return pts