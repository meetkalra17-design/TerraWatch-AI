"""Builds and persists an Analysis from a before/after image pair."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.lib.db import db
from backend.lib.flood_engine import analyze, flood_polygon, severity_for
from backend.models.analysis import Analysis, Infrastructure

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def to_analysis(doc: dict) -> Analysis:
    doc = {k: v for k, v in doc.items() if k != "_id"}
    ca = doc["created_at"]
    if ca.tzinfo is None:
        doc["created_at"] = ca.replace(tzinfo=timezone.utc)
    return Analysis(**doc)


async def create_analysis(
    *,
    before: bytes,
    after: bytes,
    before_ext: str,
    after_ext: str,
    region: str,
    lat: float,
    lng: float,
    before_date: str,
    after_date: str,
    scene_area_km2: float,
    population_density: float,
    created_by: str,
    pct_scale: float = 1.0,
    created_at: datetime | None = None,
) -> Analysis:
    aid = str(uuid.uuid4())
    b_name, a_name, m_name = f"{aid}_before{before_ext}", f"{aid}_after{after_ext}", f"{aid}_mask.png"
    (UPLOAD_DIR / b_name).write_bytes(before)
    (UPLOAD_DIR / a_name).write_bytes(after)
    metrics = analyze(before, after, UPLOAD_DIR / m_name)

    pct = round(min(metrics["flooded_pct"] * pct_scale, 95.0), 2)
    area = round(scene_area_km2 * pct / 100, 2)
    population = int(area * population_density)
    analysis = Analysis(
        id=aid,
        region=region,
        lat=lat,
        lng=lng,
        before_date=before_date,
        after_date=after_date,
        before_image=f"/api/uploads/{b_name}",
        after_image=f"/api/uploads/{a_name}",
        mask_image=f"/api/uploads/{m_name}",
        scene_area_km2=scene_area_km2,
        population_density=population_density,
        flooded_pct=pct,
        water_before_pct=metrics["water_before_pct"],
        water_after_pct=round(metrics["water_before_pct"] + pct, 2),
        change_pct=metrics["change_pct"],
        flooded_area_km2=area,
        affected_population=population,
        severity=severity_for(pct),
        confidence=metrics["confidence"],
        polygon=flood_polygon(lat, lng, area, aid),
        infrastructure=Infrastructure(
            roads_km=round(area * 1.8, 1),
            buildings=int(population / 4.8),
            cropland_km2=round(area * 0.55, 2),
        ),
        created_by=created_by,
        created_at=created_at or datetime.now(timezone.utc),
    )
    await db.analyses.insert_one(analysis.model_dump())
    return analysis