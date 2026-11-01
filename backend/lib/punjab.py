"""Static Punjab (India) reference data: districts, census population, river gauges, flood events."""

import json
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

# Census 2011 population (post-2011 district splits; Malerkotla is inside Sangrur on 2011 boundaries)
POPULATION = {
    "Amritsar": 2490656, "Barnala": 595527, "Bathinda": 1388525, "Faridkot": 617508,
    "Fatehgarh Sahib": 600163, "Fazilka": 1180483, "Ferozepur": 965337, "Gurdaspur": 1621725,
    "Hoshiarpur": 1586625, "Jalandhar": 2193590, "Kapurthala": 815168, "Ludhiana": 3498739,
    "Mansa": 769751, "Moga": 995746, "Sri Muktsar Sahib": 901896, "Pathankot": 676598,
    "Patiala": 1895686, "Rupnagar": 684627, "S.A.S. Nagar": 994628, "Sangrur": 1655169,
    "Shahid Bhagat Singh Nagar": 612310, "Tarn Taran": 1119627,
}

# GloFAS river cells (snapped to the highest-discharge 5 km cell near each gauge site)
STATIONS = {
    "ravi-madhopur": {"name": "Ravi @ Madhopur", "river": "Ravi", "lat": 32.27, "lng": 75.45},
    "ravi-dbn": {"name": "Ravi @ Dera Baba Nanak", "river": "Ravi", "lat": 32.08, "lng": 74.92},
    "beas-mukerian": {"name": "Beas @ Mukerian", "river": "Beas", "lat": 31.80, "lng": 75.52},
    "beas-dhilwan": {"name": "Beas @ Dhilwan", "river": "Beas", "lat": 31.40, "lng": 75.19},
    "sutlej-ropar": {"name": "Sutlej @ Ropar", "river": "Sutlej", "lat": 30.97, "lng": 76.37},
    "sutlej-phillaur": {"name": "Sutlej @ Phillaur", "river": "Sutlej", "lat": 30.97, "lng": 75.64},
    "sutlej-harike": {"name": "Sutlej @ Harike", "river": "Sutlej", "lat": 31.15, "lng": 74.80},
    "sutlej-fazilka": {"name": "Sutlej @ Fazilka", "river": "Sutlej", "lat": 30.40, "lng": 73.88},
    "ghaggar-khanauri": {"name": "Ghaggar @ Khanauri", "river": "Ghaggar", "lat": 29.82, "lng": 75.97},
    "ghaggar-sardulgarh": {"name": "Ghaggar @ Sardulgarh", "river": "Ghaggar", "lat": 29.59, "lng": 75.09},
}

DISTRICT_STATION = {
    "Pathankot": "ravi-madhopur", "Gurdaspur": "ravi-dbn", "Amritsar": "ravi-dbn",
    "Hoshiarpur": "beas-mukerian", "Kapurthala": "beas-dhilwan", "Jalandhar": "sutlej-phillaur",
    "Tarn Taran": "sutlej-harike", "Shahid Bhagat Singh Nagar": "sutlej-phillaur", "Rupnagar": "sutlej-ropar",
    "S.A.S. Nagar": "sutlej-ropar", "Fatehgarh Sahib": "sutlej-ropar", "Ludhiana": "sutlej-phillaur",
    "Moga": "sutlej-harike", "Ferozepur": "sutlej-harike", "Fazilka": "sutlej-fazilka",
    "Faridkot": "sutlej-fazilka", "Sri Muktsar Sahib": "sutlej-fazilka", "Bathinda": "ghaggar-sardulgarh",
    "Mansa": "ghaggar-sardulgarh", "Barnala": "ghaggar-khanauri", "Sangrur": "ghaggar-khanauri",
    "Patiala": "ghaggar-khanauri",
}

# Documented Punjab flood events used for risk calibration / held-out evaluation
FLOOD_EVENTS = [
    {"id": "2019-sutlej", "name": "Aug 2019 Sutlej floods (Bhakra release)", "start": "2019-08-17", "end": "2019-08-28",
     "districts": ["Jalandhar", "Kapurthala", "Ferozepur", "Rupnagar", "Ludhiana", "Moga", "Shahid Bhagat Singh Nagar", "Tarn Taran", "Fazilka"]},
    {"id": "2023-monsoon", "name": "Jul 2023 monsoon floods (Ghaggar, Sutlej)", "start": "2023-07-08", "end": "2023-07-22",
     "districts": ["Patiala", "S.A.S. Nagar", "Rupnagar", "Sangrur", "Fatehgarh Sahib", "Jalandhar", "Kapurthala", "Ferozepur",
                   "Fazilka", "Tarn Taran", "Mansa", "Moga", "Ludhiana", "Hoshiarpur", "Shahid Bhagat Singh Nagar"]},
    {"id": "2025-ravi-beas", "name": "Aug-Sep 2025 Ravi/Beas/Sutlej floods", "start": "2025-08-24", "end": "2025-09-10",
     "districts": ["Gurdaspur", "Amritsar", "Pathankot", "Kapurthala", "Ferozepur", "Fazilka", "Tarn Taran", "Hoshiarpur",
                   "Rupnagar", "S.A.S. Nagar", "Patiala", "Sangrur", "Mansa", "Moga", "Ludhiana", "Barnala", "Jalandhar"]},
]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float, float]:
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    a *= 0.5
    if abs(a) < 1e-12:
        return ring[0][0], ring[0][1], 0.0
    return cx / (6 * a), cy / (6 * a), abs(a)


@lru_cache
def geojson() -> dict:
    path = DATA / "punjab_districts.geojson"
    if not path.exists():
        path = DATA / "punjab_districts.geojson.txt"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def districts() -> list[dict]:
    """[{name, slug, lat, lng, bbox, population, station}] sorted by name."""
    out = []
    for f in geojson()["features"]:
        name = f["properties"]["district"]
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        best = max((_ring_centroid(p[0]) for p in polys), key=lambda t: t[2])
        xs = [pt[0] for p in polys for pt in p[0]]
        ys = [pt[1] for p in polys for pt in p[0]]
        out.append({
            "name": name, "slug": slugify(name), "lat": round(best[1], 4), "lng": round(best[0], 4),
            "bbox": [min(xs), min(ys), max(xs), max(ys)], "population": POPULATION.get(name, 0),
            "station": DISTRICT_STATION.get(name, "sutlej-phillaur"),
        })
    return sorted(out, key=lambda d: d["name"])


def by_slug(slug: str) -> dict | None:
    return next((d for d in districts() if d["slug"] == slug), None)