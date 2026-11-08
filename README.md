# UrbanTwin

AI-assisted urban intelligence and digital-twin platform for **Noakhali Paurashava**, Bangladesh (university lab project).

One FastAPI + PostgreSQL/PostGIS backend and one React/MapLibre frontend, organised as six connected modules:

| # | Module | What it does | Where |
|---|--------|--------------|-------|
| 1 | **City Monitor** | Citizen reports with photos + GPS, map, filters, status | `/`, `/track`, `/dashboard` |
| 2 | **City Investigator** | Duplicate scoring (distance, category, text, image hash, time) and human verification | `/investigator` |
| 3 | **City Intelligence** | Links verified issues to nearest road/drain/water/ward, recurrence flags, graph | `/intelligence` |
| 4 | **City Planner** | Indicative costs, priority scores, budget packs (greedy + OR-Tools optimal) | `/planner` |
| 5 | **City Accountability** | Approved projects, progress, completion evidence, inspections, recurrence screening | `/accountability` |
| 6 | **City Simulation** | Green-space accessibility scenarios and repair-budget scenarios | `/simulation` |

Plus `/overview` (live counts), `/admin` (dataset register + audit log).
See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md), [`docs/LAB_QA.md`](docs/LAB_QA.md) and [`docs/FEATURE_STATUS.md`](docs/FEATURE_STATUS.md) (what is real, simplified, or not built).

## Data honesty

* Roads, buildings, water come from **OpenStreetMap (ODbL)**. OSM has **no drains** for this area.
* Wards are a **demonstration 3x3 grid**, not official wards. Costs are **placeholder rates**, not PWD/LGED schedules.
* `scripts/seed_demo.py` creates synthetic records, every one flagged `is_demo` and labelled DEMO in the UI.
* A *report* is a submission, an *issue* exists only after human verification, a *project* is approved works.
* Accountability output is a screening signal for independent review, never an allegation.

## Requirements

Python 3.13, Node.js 22, PostgreSQL 17 + PostGIS (the author's PostgreSQL listens on **port 5433**).

## Setup (Windows PowerShell)

```powershell
# 1. Database (once)
& "D:\Program Files\PostgreSQL\17\bin\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d postgres -c "CREATE DATABASE urbantwin;"
& "D:\Program Files\PostgreSQL\17\bin\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d urbantwin -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# 2. Backend  (from D:\Urbantwin\backend)
copy ..\.env.example .env        # then edit: password, STAFF_TOKEN
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head             # creates / upgrades every table (safe on an existing database)

# 3. Real map data (needs internet; run once)
python -u scripts\import_osm_noakhali.py
python -u scripts\import_osm_green.py        # optional: OSM parks/grass for City Simulation

# 4. Demo records so every module has something to show (optional, clearly labelled DEMO)
python scripts\seed_demo.py                  # add --reset to recreate

# 5. Run the API
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, second terminal (from `D:\Urbantwin\frontend`):

```powershell
npm install
npm run dev
```

Open http://localhost:5173. Citizens use `/` and `/track`. For the staff pages click **Staff login** (top right) and enter your `STAFF_TOKEN` plus your name; the name is written to the audit log.

> Upgrading from the Phase 0-5 code? Just run `alembic upgrade head`; it adds the new tables and columns without touching your data. If `STAFF_TOKEN` is empty the staff login is **off** and `/api/health` says so.

## Tests

```powershell
cd D:\Urbantwin\backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

Tests never touch your real database: they create and use `urbantwin_test` (your `CREATE DATABASE` right is needed once), seed a tiny labelled geography, and write uploads to a temp folder. The run aborts if the database name does not end in `_test`.

Frontend type-check and build: `cd frontend; npm run build`.

## API quick reference

Interactive docs: http://127.0.0.1:8000/docs . Public: `POST /api/reports`, `GET /api/reports/track/{id}`, `GET /api/reports/meta`, `GET /api/geo/*`, `GET /api/health`. Everything else needs `X-Staff-Token`:
`/api/investigator/*`, `/api/intelligence/*`, `/api/planner/*`, `/api/accountability/*`, `/api/simulation/*`, `/api/overview`, `/api/audit`, `/api/data-sources`.

## Security notes

Never commit `backend/.env`. Uploads are limited to JPEG/PNG/WebP by file signature (not file name), 5 MB each, 3 per report, stored under random names. The staff token is a single shared lab credential: fine for a demonstration, replace with per-user accounts (and HTTPS) before any real deployment.
