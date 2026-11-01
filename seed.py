"""Idempotent seed: demo operator + sample flood analyses. Run: cd /app/backend && python seed.py"""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend.lib.analysis_service import create_analysis
from backend.lib.auth import hash_password
from backend.lib.dates import today_iso
from backend.lib.db import db, ensure_indexes

SAMPLES = Path(__file__).parent / "uploads" / "samples"

DEMO_USERS = [
    ("Mission Operator", "operator@terrawatch.ai", "Terra@2026", "operator"),
    ("Field Analyst", "analyst@terrawatch.ai", "Analyst@2026", "analyst"),
]

# region, lat, lng, sample pair, scene km2, density, pct scale, days ago
SEEDS = [
    ("Brahmaputra Basin, Assam", 26.18, 91.74, 3, 420, 410, 1.85, 3),
    ("Kosi River, Bihar", 25.88, 86.62, 1, 360, 1100, 1.15, 8),
    ("Mahanadi Delta, Odisha", 20.30, 86.45, 2, 310, 690, 1.0, 13),
    ("Godavari Delta, Andhra Pradesh", 16.71, 81.92, 2, 280, 520, 0.6, 20),
    ("Periyar Basin, Kerala", 10.12, 76.38, 3, 190, 860, 1.2, 27),
    ("Yamuna Floodplain, Delhi", 28.62, 77.27, 1, 120, 2400, 0.25, 36),
    ("Ganga at Patna, Bihar", 25.61, 85.14, 1, 240, 1100, 0.85, 45),
    ("Sundarbans, West Bengal", 21.95, 88.85, 2, 330, 300, 1.9, 58),
]


async def main() -> None:
    await ensure_indexes()
    for name, email, pw, role in DEMO_USERS:
        if not await db.users.find_one({"email": email}):
            await db.users.insert_one({
                "id": str(uuid.uuid4()), "name": name, "email": email, "role": role,
                "password_hash": hash_password(pw), "created_at": datetime.now(timezone.utc),
            })
            print("created user", email)

    if await db.analyses.count_documents({"seeded": True}) == 0 and await db.analyses.count_documents({}) == 0:
        today = date.fromisoformat(today_iso())
        for region, lat, lng, pair, area, dens, scale, ago in SEEDS:
            after_d = today - timedelta(days=ago)
            before_d = after_d - timedelta(days=24)
            a = await create_analysis(
                before=(SAMPLES / f"pair{pair}_before.jpg").read_bytes(),
                after=(SAMPLES / f"pair{pair}_after.jpg").read_bytes(),
                before_ext=".jpg", after_ext=".jpg",
                region=region, lat=lat, lng=lng,
                before_date=before_d.isoformat(), after_date=after_d.isoformat(),
                scene_area_km2=area, population_density=dens,
                created_by="Mission Operator", pct_scale=scale,
                created_at=datetime.now(timezone.utc) - timedelta(days=ago),
            )
            await db.analyses.update_one({"id": a.id}, {"$set": {"seeded": True}})
            print("seeded", region, a.severity, a.flooded_pct)
    print("done")


if __name__ == "__main__":
    asyncio.run(main())