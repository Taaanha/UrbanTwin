# UrbanTwin

AI-powered urban intelligence platform for **Noakhali Paurashava**, Bangladesh. University lab project.

Phase 0 delivers a runnable skeleton: FastAPI + PostgreSQL 17 / PostGIS + a MapLibre map that proves the frontend can reach the backend.

## Requirements

- Python 3.13
- Node.js 22
- PostgreSQL 17 with PostGIS (on this machine PostgreSQL 17 listens on **port 5433**)

## Setup

1. Copy `.env.example` to `backend/.env` and set your database password.
2. Create the database and enable PostGIS:

```powershell
& "D:\Program Files\PostgreSQL\17\bin\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d postgres -c "CREATE DATABASE urbantwin;"
& "D:\Program Files\PostgreSQL\17\bin\psql.exe" -h 127.0.0.1 -p 5433 -U postgres -d urbantwin -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

3. Backend (from `D:\Urbantwin\backend`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

4. Frontend (from `D:\Urbantwin\frontend`, second terminal):

```powershell
npm install
npm run dev
```

Open http://localhost:5173 — the header should show **API + PostGIS connected**.

## Test

From `D:\Urbantwin\backend` with the venv active:

```powershell
python -m pytest tests\test_health.py
```

## Security

Never commit `backend/.env`. It contains the database password.
