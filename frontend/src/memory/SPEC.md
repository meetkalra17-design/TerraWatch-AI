# TerraWatch AI — Spec

Satellite flood-intelligence dashboard (hackathon project). Dark "mission control" UI.

## Stack
FastAPI + Mongo (motor) backend, Vite React 19 + Tailwind v4 + shadcn (base-ui) frontend.
Leaflet + react-leaflet (CARTO dark tiles over OpenStreetMap), recharts, jsPDF.

## Auth
Email/password, bcrypt hash, httpOnly cookie `tw_session` (sessions collection, 7-day TTL).
All app routes require login; `/login`, `/register` public. Credentials: memory/test_credentials.md.

## Data model
- users {id, name, email, role, password_hash}
- sessions {token, user_id, expires_at}
- analyses (models/analysis.py :: Analysis) — region, lat/lng, before/after dates, image URLs
  (`/api/uploads/<id>_before|after.*`, `<id>_mask.png`), flooded_pct, water_before/after_pct,
  change_pct, flooded_area_km2, affected_population, severity (low|moderate|high|critical),
  confidence, polygon [[lat,lng]...], infrastructure {roads_km, buildings, cropland_km2}.
  Analyses are shared across all users (org-wide mission archive).

## Flood engine (SIMULATED, no external API) — backend/lib/flood_engine.py
Pseudo-MNDWI on RGB: water-like = smooth texture AND (bluish | muddy | dark). Flood = water in
after, not in before, with colour change. Severity: ≥30% critical, ≥18% high, ≥8% moderate.
Area = scene_area × pct; population = area × density. Polygon is a synthetic ring around lat/lng.

## API (all under /api)
POST /auth/register, /auth/login, /auth/logout; GET /auth/me
POST /analyses (multipart: before, after, region, lat, lng, before_date, after_date, scene_area_km2, population_density)
GET /analyses, GET/DELETE /analyses/{id}
GET /dashboard/stats (KPIs, 10-week trend, severity breakdown, alerts, recent)
GET /reports/analyses.csv, GET /reports/{id}.csv
GET /uploads/{path} (images; samples at /uploads/samples/pair{1,2,3}_{before,after}.jpg)

## Pages
/login, /register, / (dashboard), /upload (dual dropzone + 3 sample datasets), /compare[/:id]
(drag slider, mask toggle/opacity/colormap), /map (?focus=id; severity filters, polygons, pulse markers),
/reports (search, filter, CSV export, delete), /reports/:id (metrics, imagery, mini map, PDF + CSV).

## Seed (cd /app/backend && python seed.py — idempotent)
2 users; 8 analyses across Indian basins (Assam, Bihar Kosi, Odisha, Godavari, Kerala, Delhi Yamuna,
Patna, Sundarbans) generated from the 3 sample pairs with a pct scale factor for variety
(3 critical, 2 high, 2 moderate, 1 low).