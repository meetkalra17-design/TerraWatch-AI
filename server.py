import asyncio
import json
import csv
import re
import time
from contextlib import asynccontextmanager
from datetime import date
from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List
import uuid
from datetime import datetime
import httpx
import numpy as np
from backend.lib.punjab import DATA, STATIONS, districts
from backend.ml.calibrate_risk import rolling_sum
from xgboost import XGBClassifier


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
from backend.lib.db import client, db, ensure_indexes


# Startup runs before the yield, shutdown after it. Add your own setup/teardown here.
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.index_task = asyncio.create_task(ensure_indexes())  # background: a big index build must not block boot
    yield
    client.close()


# Create the main app without a prefix
app = FastAPI(lifespan=lifespan)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")
MODEL_PATH = ROOT_DIR / "backend" / "ml" / "artifacts" / "flood_risk_xgboost.json"
MODEL_FEATURES = [
    "log_rain1", "log_rain3", "log_rain7", "log_rain30", "temp_mean7",
    "rain_days7", "rain_peak3", "discharge_change3", "discharge_max7",
    "log_q_ratio", "log_q_ratio_max3", "month_sin", "month_cos",
]
_MODEL: XGBClassifier | None = None
_FORECAST_CACHE: tuple[float, dict] | None = None
_FORECAST_CACHE_TTL_SECONDS = 300
_FORECAST_LOCK = asyncio.Lock()
_STATION_NORMALS: dict[str, float] | None = None
_EVENT_PRIORS: dict[str, list[tuple[date, date]]] | None = None
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
OLLAMA_MODEL_CANDIDATES = ("gemma3:4b", "qwen3:4b", "qwen3:8b", "llama3.1:8b")
_OLLAMA_SELECTED_MODEL: str | None = None
INDIA_FORECAST_CITIES = [
    ("Visakhapatnam", "Andhra Pradesh", 17.6868, 83.2185),
    ("Itanagar", "Arunachal Pradesh", 27.0844, 93.6053),
    ("Guwahati", "Assam", 26.1445, 91.7362),
    ("Patna", "Bihar", 25.5941, 85.1376),
    ("Raipur", "Chhattisgarh", 21.2514, 81.6296),
    ("Panaji", "Goa", 15.4909, 73.8278),
    ("Ahmedabad", "Gujarat", 23.0225, 72.5714),
    ("Gurugram", "Haryana", 28.4595, 77.0266),
    ("Shimla", "Himachal Pradesh", 31.1048, 77.1734),
    ("Ranchi", "Jharkhand", 23.3441, 85.3096),
    ("Bengaluru", "Karnataka", 12.9716, 77.5946),
    ("Kochi", "Kerala", 9.9312, 76.2673),
    ("Bhopal", "Madhya Pradesh", 23.2599, 77.4126),
    ("Mumbai", "Maharashtra", 19.0760, 72.8777),
    ("Imphal", "Manipur", 24.8170, 93.9368),
    ("Shillong", "Meghalaya", 25.5788, 91.8933),
    ("Aizawl", "Mizoram", 23.7271, 92.7176),
    ("Kohima", "Nagaland", 25.6751, 94.1086),
    ("Bhubaneswar", "Odisha", 20.2961, 85.8245),
    ("Jaipur", "Rajasthan", 26.9124, 75.7873),
    ("Gangtok", "Sikkim", 27.3389, 88.6065),
    ("Chennai", "Tamil Nadu", 13.0827, 80.2707),
    ("Hyderabad", "Telangana", 17.3850, 78.4867),
    ("Agartala", "Tripura", 23.8315, 91.2868),
    ("Lucknow", "Uttar Pradesh", 26.8467, 80.9462),
    ("Dehradun", "Uttarakhand", 30.3165, 78.0322),
    ("Kolkata", "West Bengal", 22.5726, 88.3639),
    ("Port Blair", "Andaman and Nicobar Islands", 11.6234, 92.7265),
    ("Chandigarh", "Chandigarh", 30.7333, 76.7794),
    ("Daman", "Dadra and Nagar Haveli and Daman and Diu", 20.3974, 72.8328),
    ("New Delhi", "Delhi", 28.6139, 77.2090),
    ("Srinagar", "Jammu and Kashmir", 34.0837, 74.7973),
    ("Leh", "Ladakh", 34.1526, 77.5771),
    ("Kavaratti", "Lakshadweep", 10.5669, 72.6420),
    ("Puducherry", "Puducherry", 11.9416, 79.8083),
]


async def _forecast_json(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    response = await client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def _prediction_model() -> XGBClassifier:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if not MODEL_PATH.exists():
        raise RuntimeError("The trained flood-risk model artifact is missing.")
    model = XGBClassifier()
    model.load_model(str(MODEL_PATH))
    _MODEL = model
    return _MODEL


def _station_normals() -> dict[str, float]:
    global _STATION_NORMALS
    if _STATION_NORMALS is not None:
        return _STATION_NORMALS
    normals: dict[str, float] = {}
    for station_id in STATIONS:
        path = DATA / "punjab_hist" / f"q_{station_id}.json"
        if not path.exists():
            continue
        values = [value for value in json.loads(path.read_text()).get("river_discharge", []) if value is not None]
        if values:
            normals[station_id] = max(float(np.median(values)), 1.0)
    _STATION_NORMALS = normals
    return normals


def _normalize_location(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower()).replace("district", "").strip()


def _event_priors() -> dict[str, list[tuple[date, date]]]:
    global _EVENT_PRIORS
    if _EVENT_PRIORS is not None:
        return _EVENT_PRIORS
    path = DATA / "IndiaFloodInventory.csv"
    priors: dict[str, list[tuple[date, date]]] = {}
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    start = datetime.strptime(row["Start Date"].split(" ")[0], "%d/%m/%y").date()
                    end = datetime.strptime(row["End Date"].split(" ")[0], "%d/%m/%y").date()
                except (KeyError, ValueError):
                    continue
                for name in (row.get("Districts") or "").split(","):
                    key = _normalize_location(name)
                    if key:
                        priors.setdefault(key, []).append((start, end))
    _EVENT_PRIORS = priors
    return priors


def _prior_features(city: str) -> list[float]:
    today = date.today()
    events = [event for event in _event_priors().get(_normalize_location(city), []) if event[1] < today]
    days = sum((end - start).days + 1 for start, end in events)
    recent = sum(start >= today.replace(year=today.year - 3) for start, _ in events)
    return [float(np.log1p(min(len(events), 50))), float(np.log1p(min(days, 365))), float(min(recent, 10))]


class RescueChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1200)
    zones: list[dict] = Field(default_factory=list, max_length=12)


def _rescue_system_prompt() -> str:
    return (
        "You are TerraWatch Rescue Copilot, an emergency-planning assistant. "
        "Answer only from the supplied map estimates and the user's question. "
        "Never claim live knowledge, verified people counts, safe roads, weather, "
        "water depth, or field conditions. Call estimates modeled and tell teams "
        "what must be verified. Give concise operational steps, prioritizing life "
        "safety, official incident command, evacuation, medical needs, communications, "
        "and withdrawal routes. Never tell responders to enter moving water or bypass "
        "official emergency procedures. If the context is insufficient, say so and "
        "ask for the missing field information. Do not invent locations, resources, "
        "or contacts. Format answers with a short situation assessment followed by "
        "numbered actions when a plan is requested. Keep the answer under 250 words "
        "and end with a single 'VERIFY BEFORE DISPATCH' line."
    )


async def _ollama_model(client: httpx.AsyncClient) -> str:
    global _OLLAMA_SELECTED_MODEL
    if _OLLAMA_SELECTED_MODEL:
        return _OLLAMA_SELECTED_MODEL
    response = await client.get(f"{OLLAMA_URL.rstrip('/')}/api/tags")
    response.raise_for_status()
    installed = {
        item.get("name")
        for item in response.json().get("models", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    for candidate in (OLLAMA_MODEL, *OLLAMA_MODEL_CANDIDATES):
        if candidate in installed:
            _OLLAMA_SELECTED_MODEL = candidate
            return candidate
    raise RuntimeError("No supported rescue model is installed in Ollama.")


@api_router.get("/predictions/flood")
async def flood_predictions():
    global _FORECAST_CACHE
    now = time.monotonic()
    if _FORECAST_CACHE and now - _FORECAST_CACHE[0] < _FORECAST_CACHE_TTL_SECONDS:
        return _FORECAST_CACHE[1]
    async with _FORECAST_LOCK:
        now = time.monotonic()
        if _FORECAST_CACHE and now - _FORECAST_CACHE[0] < _FORECAST_CACHE_TTL_SECONDS:
            return _FORECAST_CACHE[1]
        response = await _build_flood_predictions()
        _FORECAST_CACHE = (time.monotonic(), response)
        return response


async def _build_flood_predictions() -> dict:
    model = _prediction_model()
    async def predict_location(client: httpx.AsyncClient, location: dict) -> dict:
        weather, river = await asyncio.gather(
            _forecast_json(client, "https://api.open-meteo.com/v1/forecast", {
                "latitude": location["lat"], "longitude": location["lng"],
                "daily": "precipitation_sum,temperature_2m_max",
                "forecast_days": 7, "timezone": "Asia/Kolkata",
            }),
            _forecast_json(client, "https://flood-api.open-meteo.com/v1/flood", {
                "latitude": location["lat"], "longitude": location["lng"],
                "daily": "river_discharge", "forecast_days": 7,
            }),
        )
        daily = weather.get("daily", {})
        rain = np.asarray([value or 0.0 for value in daily.get("precipitation_sum", [])], dtype=float)
        temp = np.asarray([value or 0.0 for value in daily.get("temperature_2m_max", [])], dtype=float)
        if len(rain) < 7 or len(temp) < 7:
            raise RuntimeError(f"Incomplete weather forecast for {location['city']}.")
        discharge = np.asarray([value or 0.0 for value in river.get("daily", {}).get("river_discharge", [])], dtype=float)
        if len(discharge) < 7:
            raise RuntimeError(f"Incomplete river forecast for {location['city']}.")
        station_normal = _station_normals().get(location["station"]) if location["station"] else None
        q_normal = station_normal or max(float(np.median(discharge)), 1.0)
        ratio = np.maximum(discharge / q_normal, 0.05)
        rain3 = rolling_sum(rain, 3)
        rain7 = rolling_sum(rain, 7)
        rain30 = rain7
        month = date.today().month
        features = np.array([[
            np.log1p(rain[-1]), np.log1p(rain3[-1]), np.log1p(rain7[-1]), np.log1p(rain30[-1]),
            float(np.mean(temp)), float(np.sum(rain >= 1.0)),
            float(np.max(rain[-3:])), max(float(ratio[-1] - ratio[-4]), 0.0),
            float(np.max(ratio)), np.log(ratio[-1]), np.log(np.max(ratio[-3:])),
            np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12),
        ]], dtype=np.float32)
        probability = float(model.predict_proba(features)[0, 1])
        return {
            "city": location["city"], "state": location["state"],
            "coverage": location["coverage"],
            "risk": round(probability * 100, 1),
            "level": "critical" if probability >= 0.5 else "high" if probability >= 0.25 else "moderate" if probability >= 0.1 else "low",
            "forecastRain7mm": round(float(np.sum(rain)), 1),
            "forecastRiverRatio": round(float(np.max(ratio)), 2),
            "lat": location["lat"], "lng": location["lng"],
        }


    limits = httpx.Limits(max_connections=12, max_keepalive_connections=12)
    locations = [
        {
            "city": district["name"], "state": "Punjab", "lat": district["lat"], "lng": district["lng"],
            "coverage": "trained", "station": district["station"],
        }
        for district in districts()
    ] + [
        {"city": city, "state": state, "lat": lat, "lng": lng, "coverage": "exploratory", "station": None}
        for city, state, lat, lng in INDIA_FORECAST_CITIES
    ]
    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        results = await asyncio.gather(
            *(predict_location(client, location) for location in locations),
            return_exceptions=True,
        )
    output = [result for result in results if isinstance(result, dict)]
    failures = [str(result) for result in results if isinstance(result, Exception)]
    if not output:
        raise RuntimeError(f"No location forecasts were available: {failures[0] if failures else 'unknown error'}")
    return {
        "model": "tw-flood-xgb-20261031",
        "scope": "Punjab trained districts plus representative cities across India",
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "horizonDays": 7,
        "predictions": sorted(output, key=lambda item: item["risk"], reverse=True),
        "warning": "Punjab scores use trained geographic coverage. Other cities are exploratory model extrapolations and are not India-wide validation. Confirm with official authorities and field observations.",
        "unavailableDistricts": len(failures),
    }


@api_router.post("/rescue/chat")
async def rescue_chat(request: RescueChatRequest):
    context = json.dumps(request.zones[:12], ensure_ascii=True)
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            model = await _ollama_model(client)
            payload = {
                "model": model,
                "stream": False,
                "think": False,
                "keep_alive": "10m",
                "messages": [
                    {"role": "system", "content": _rescue_system_prompt()},
                    {
                        "role": "user",
                        "content": f"Current map estimates (not field-verified): {context}\n\nQuestion: {request.question}",
                    },
                ],
                "options": {"temperature": 0.1, "top_p": 0.8, "num_ctx": 8192},
            }
            response = await client.post(f"{OLLAMA_URL.rstrip('/')}/api/chat", json=payload)
            response.raise_for_status()
            result = response.json()
        answer = result.get("message", {}).get("content")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Ollama returned an empty response.")
        if "</think>" in answer:
            answer = answer.rsplit("</think>", 1)[-1].strip()
        return {"answer": answer.strip(), "provider": "ollama", "model": model, "grounded": True}
    except (httpx.HTTPError, ValueError, RuntimeError) as error:
        logger.warning("Rescue copilot unavailable: %r", error)
        raise HTTPException(status_code=503, detail="Local rescue copilot unavailable.")


# Define Models
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.model_dump())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

from backend.routers.auth import router as auth_router
from backend.routers.analyses import router as analyses_router

api_router.include_router(auth_router)
api_router.include_router(analyses_router)

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)