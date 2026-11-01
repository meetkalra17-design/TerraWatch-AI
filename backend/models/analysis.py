from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Severity = Literal["low", "moderate", "high", "critical"]


class Infrastructure(BaseModel):
    roads_km: float
    buildings: int
    cropland_km2: float


class Analysis(BaseModel):
    id: str
    region: str
    lat: float
    lng: float
    before_date: str
    after_date: str
    before_image: str
    after_image: str
    mask_image: str
    scene_area_km2: float
    population_density: float
    flooded_pct: float
    water_before_pct: float
    water_after_pct: float
    change_pct: float
    flooded_area_km2: float
    affected_population: int
    severity: Severity
    confidence: float
    polygon: list[list[float]]
    infrastructure: Infrastructure
    created_by: str
    created_at: datetime


class TrendPoint(BaseModel):
    week: str
    flooded_km2: float
    analyses: int


class SeverityCount(BaseModel):
    severity: Severity
    count: int


class DashboardStats(BaseModel):
    total_analyses: int
    total_flooded_km2: float
    critical_zones: int
    regions_monitored: int
    affected_population: int
    avg_confidence: float
    today: str
    trend: list[TrendPoint]
    severity_breakdown: list[SeverityCount]
    alerts: list[Analysis]
    recent: list[Analysis]