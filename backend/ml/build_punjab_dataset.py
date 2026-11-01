"""Builds the Punjab-specific weakly-labelled training set from Sentinel-2 L2A.

Source: Microsoft Planetary Computer (free, no account). For flood-prone river
reaches across Punjab (India) we fetch the clearest scene inside each flood
window (July 2023, Aug-Sep 2025) plus a dry-season reference, and derive weak
water labels from the L2A Scene Classification (SCL=6 water) combined with
MNDWI = (B03-B11)/(B03+B11) > 0.12. Clouds / shadows / no-data become -1.

Run: cd /app/backend && python -m ml.build_punjab_dataset   (writes /root/punjab_s2/*.npz)
"""

import json
import time
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

import numpy as np
import tifffile

OUT = Path("/root/punjab_s2")
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
DATA = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"

SITES = {
    "harike": (31.15, 74.95), "ferozepur": (30.95, 74.62), "fazilka": (30.40, 74.05),
    "dera_baba_nanak": (32.03, 75.03), "kapurthala_beas": (31.42, 75.30), "ludhiana_sutlej": (31.01, 75.83),
    "rupnagar": (30.97, 76.52), "patiala_ghaggar": (30.12, 76.25), "khanauri": (29.83, 75.98),
    "sardulgarh": (29.69, 75.24), "pathankot": (32.30, 75.62), "tarn_taran_beas": (31.37, 75.08),
    "sultanpur_lodhi": (31.21, 75.20),
}
WINDOWS = {"flood2023": "2023-07-10/2023-07-31", "flood2025": "2025-08-27/2025-09-20", "dry2024": "2024-03-01/2024-04-20"}
HALF = 0.07  # ~15 km box


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def best_item(lat: float, lng: float, window: str) -> dict | None:
    d = _post(STAC, {
        "collections": ["sentinel-2-l2a"],
        "intersects": {"type": "Point", "coordinates": [lng, lat]},
        "datetime": window, "limit": 50, "query": {"eo:cloud_cover": {"lt": 60}},
    })
    feats = sorted(d.get("features", []), key=lambda f: f["properties"]["eo:cloud_cover"])
    return feats[0] if feats else None


def fetch_bands(item_id: str, lat: float, lng: float) -> np.ndarray:
    bbox = f"{lng - HALF},{lat - HALF},{lng + HALF},{lat + HALF}"
    q = [("collection", "sentinel-2-l2a"), ("item", item_id)] + [("assets", a) for a in ("B04", "B03", "B02", "B08", "B11", "SCL")]
    url = f"{DATA}/{bbox}/512x512.tif?" + urllib.parse.urlencode(q)
    raw = urllib.request.urlopen(url, timeout=120).read()
    return tifffile.imread(BytesIO(raw))  # (512, 512, 7) last = mask


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for site, (lat, lng) in SITES.items():
        for wname, window in WINDOWS.items():
            out = OUT / f"{site}_{wname}.npz"
            if out.exists():
                continue
            try:
                it = best_item(lat, lng, window)
                if not it:
                    print("no scene", site, wname)
                    continue
                a = fetch_bands(it["id"], lat, lng).astype(np.float32)
                b4, b3, b2, b8, b11, scl, valid = (a[..., i] for i in range(7))
                rgb = np.clip(np.stack([b4, b3, b2], -1) * 255 / 3000, 0, 255).astype(np.uint8)
                mndwi = (b3 - b11) / (b3 + b11 + 1e-6)
                ndwi = (b3 - b8) / (b3 + b8 + 1e-6)
                water = (scl == 6) | ((mndwi > 0.12) & (ndwi > -0.05))
                label = water.astype(np.int8)
                bad = (valid == 0) | np.isin(scl, [0, 1, 3, 8, 9, 10]) | (b2 == 0)
                label[bad] = -1
                np.savez_compressed(out, rgb=rgb, label=label, item=it["id"], cloud=it["properties"]["eo:cloud_cover"])
                print(site, wname, it["id"], f"water={float((label == 1).mean()):.3f} invalid={float(bad.mean()):.2f}")
            except Exception as e:  # keep going on transient errors
                print("ERR", site, wname, e)
            time.sleep(0.3)


if __name__ == "__main__":
    main()