import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image

from backend.lib.analysis_service import UPLOAD_DIR, create_analysis, to_analysis
from backend.lib.auth import current_user
from backend.lib.dates import today_iso
from backend.lib.db import db
from backend.models.analysis import Analysis, DashboardStats, SeverityCount, TrendPoint
from backend.models.auth import User

router = APIRouter(tags=["analyses"])

MAX_BYTES = 15 * 1024 * 1024
EXTS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "TIFF": ".tif"}


async def _read_image(f: UploadFile, label: str) -> tuple[bytes, str]:
    data = await f.read()
    if not data:
        raise HTTPException(status_code=400, detail=f"{label} image is empty")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"{label} image exceeds 15 MB")
    try:
        img = Image.open(BytesIO(data))
        fmt = img.format or "PNG"
        img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail=f"{label} file is not a valid image")
    return data, EXTS.get(fmt, ".png")


@router.post("/analyses", response_model=Analysis)
async def run_analysis(
    before: UploadFile = File(...),
    after: UploadFile = File(...),
    region: str = Form(..., min_length=2, max_length=120),
    lat: float = Form(..., ge=-90, le=90),
    lng: float = Form(..., ge=-180, le=180),
    before_date: str = Form(...),
    after_date: str = Form(...),
    scene_area_km2: float = Form(100.0, gt=0, le=100000),
    population_density: float = Form(650.0, ge=0, le=100000),
    user: User = Depends(current_user),
):
    b, b_ext = await _read_image(before, "Before")
    a, a_ext = await _read_image(after, "After")
    return await create_analysis(
        before=b, after=a, before_ext=b_ext, after_ext=a_ext,
        region=region.strip(), lat=lat, lng=lng,
        before_date=before_date, after_date=after_date,
        scene_area_km2=scene_area_km2, population_density=population_density,
        created_by=user.name,
    )


@router.get("/analyses", response_model=list[Analysis])
async def list_analyses(_: User = Depends(current_user)):
    docs = await db.analyses.find().sort("created_at", -1).to_list(500)
    return [to_analysis(d) for d in docs]


@router.get("/analyses/{id}", response_model=Analysis)
async def get_analysis(id: str, _: User = Depends(current_user)):
    doc = await db.analyses.find_one({"id": id})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return to_analysis(doc)


@router.delete("/analyses/{id}")
async def delete_analysis(id: str, _: User = Depends(current_user)):
    doc = await db.analyses.find_one({"id": id})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    await db.analyses.delete_one({"id": id})
    for key in ("before_image", "after_image", "mask_image"):
        p = UPLOAD_DIR / Path(doc[key]).name
        if p.exists() and "samples" not in str(p):
            p.unlink()
    return {"ok": True}


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(_: User = Depends(current_user)):
    docs = await db.analyses.find().sort("created_at", -1).to_list(1000)
    items = [to_analysis(d) for d in docs]
    today = date.fromisoformat(today_iso())
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=9)
    buckets: dict[str, list[float]] = {}
    for i in range(10):
        buckets[(start + timedelta(weeks=i)).isoformat()] = [0.0, 0]
    for a in items:
        try:
            d = date.fromisoformat(a.after_date[:10])
        except ValueError:
            continue
        wk = (d - timedelta(days=d.weekday())).isoformat()
        if wk in buckets:
            buckets[wk][0] += a.flooded_area_km2
            buckets[wk][1] += 1
    sev: dict[str, int] = defaultdict(int)
    for a in items:
        sev[a.severity] += 1
    return DashboardStats(
        total_analyses=len(items),
        total_flooded_km2=round(sum(a.flooded_area_km2 for a in items), 2),
        critical_zones=sum(1 for a in items if a.severity in ("critical", "high")),
        regions_monitored=len({a.region for a in items}),
        affected_population=sum(a.affected_population for a in items),
        avg_confidence=round(sum(a.confidence for a in items) / len(items), 1) if items else 0.0,
        today=today.isoformat(),
        trend=[TrendPoint(week=k, flooded_km2=round(v[0], 2), analyses=int(v[1])) for k, v in buckets.items()],
        severity_breakdown=[SeverityCount(severity=s, count=sev.get(s, 0)) for s in ("critical", "high", "moderate", "low")],
        alerts=[a for a in items if a.severity in ("critical", "high")][:6],
        recent=items[:8],
    )


CSV_COLS = [
    "id", "region", "lat", "lng", "before_date", "after_date", "severity", "flooded_pct",
    "flooded_area_km2", "scene_area_km2", "water_before_pct", "water_after_pct", "change_pct",
    "affected_population", "confidence", "roads_km", "buildings", "cropland_km2", "created_by", "created_at",
]


def _csv(items: list[Analysis], filename: str) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for a in items:
        d = a.model_dump()
        d.update(d.pop("infrastructure"))
        d["created_at"] = a.created_at.isoformat()
        w.writerow([d[c] for c in CSV_COLS])
    return Response(
        buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/analyses.csv")
async def export_all_csv(_: User = Depends(current_user)):
    docs = await db.analyses.find().sort("created_at", -1).to_list(1000)
    return _csv([to_analysis(d) for d in docs], "terrawatch_analyses.csv")


@router.get("/reports/{id}.csv")
async def export_one_csv(id: str, _: User = Depends(current_user)):
    doc = await db.analyses.find_one({"id": id})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _csv([to_analysis(doc)], f"terrawatch_report_{id[:8]}.csv")


@router.get("/uploads/{path:path}")
async def get_upload(path: str):
    p = (UPLOAD_DIR / path).resolve()
    if not str(p).startswith(str(UPLOAD_DIR.resolve())) or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})