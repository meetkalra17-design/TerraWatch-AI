"""Counts critical infrastructure per Punjab district from OpenStreetMap (Overpass API).

Uses each district's bounding box (approximation at borders). Writes data/punjab_infrastructure.json.
Run: cd /app/backend && python -m ml.build_infrastructure
"""

import json
import time

import httpx

from backend.lib.punjab import DATA, districts

URL = "https://overpass-api.de/api/interpreter"
TAGS = {
    "hospitals": 'nwr["amenity"~"^(hospital|clinic)$"]',
    "schools": 'nwr["amenity"~"^(school|college)$"]',
    "bridges": 'way["bridge"="yes"]["highway"]',
    "major_roads": 'way["highway"~"^(motorway|trunk|primary|secondary)$"]',
    "shelters": 'nwr["amenity"~"^(community_centre|place_of_worship)$"]',
}


def main() -> None:
    out_path = DATA / "punjab_infrastructure.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}
    for d in districts():
        if d["name"] in out:
            continue
        x0, y0, x1, y1 = d["bbox"]
        bb = f"({y0},{x0},{y1},{x1})"
        q = "[out:json][timeout:120];" + "".join(f"({t}{bb};);out count;" for t in TAGS.values())
        for attempt in range(4):
            try:
                r = httpx.post(URL, data={"data": q}, timeout=180)
                r.raise_for_status()
                counts = [int(e["tags"]["total"]) for e in r.json()["elements"]]
                out[d["name"]] = dict(zip(TAGS.keys(), counts))
                print(d["name"], out[d["name"]])
                break
            except Exception as e:
                print("retry", d["name"], e)
                time.sleep(15 * (attempt + 1))
        out_path.write_text(json.dumps(out, indent=1))
        time.sleep(2)


if __name__ == "__main__":
    main()