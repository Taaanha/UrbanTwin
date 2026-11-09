# Deploying UrbanTwin

UrbanTwin deploys as **one Docker container** (the React app and the FastAPI API together) plus **one PostGIS database**.
The `Dockerfile` and `render.yaml` in the project root are ready for [Render](https://render.com); any host that runs
Docker works the same way. Free tiers change, so check each provider's current limits before relying on them.

> The Docker image has **not** been built or run by the person who wrote these files (no Docker on the machine used).
> The pieces were tested separately: the API serving the built app is covered by `tests/test_deploy.py`, and the
> frontend build and backend tests pass. Do a trial deploy well before a presentation.

## What you need

* A GitHub account (Render deploys from a repository).
* A Render account.
* A hosted PostgreSQL with the **PostGIS** extension (for example Neon or Supabase, both of which offer PostGIS).
* Optional: a Gemini API key for the AI second opinion. Without it the app runs and the AI button says it is not configured.

## 1. Database

1. Create a project/database with your provider.
2. In its SQL editor run: `CREATE EXTENSION IF NOT EXISTS postgis;`
3. Copy the connection string. `postgres://` / `postgresql://` URLs work as given; the app adds the right driver itself.
   Keep `?sslmode=require` if your provider includes it.

## 2. Load the tables and map data (from your own computer, once)

In PowerShell, from `D:\Urbantwin\backend`, with the virtual environment active. Setting `DATABASE_URL` in the shell
overrides the value in `.env` for that window only:

```powershell
$env:DATABASE_URL = "<the hosted connection string>"
alembic upgrade head
python -u scripts\import_osm_noakhali.py
python -u scripts\import_osm_green.py     # optional: OSM parks for City Simulation
python scripts\seed_demo.py               # optional: clearly labelled DEMO records
```

Close that PowerShell window afterwards so the variable does not linger.

## 3. Put the code on GitHub

Create an empty (preferably private) repository, then from `D:\Urbantwin`:

```powershell
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin master
```

`.env`, uploads, test photos and the elevation cache are git-ignored, so no secrets are pushed.

## 4. Render

1. Render dashboard, **New**, **Blueprint**, pick the repository. It reads `render.yaml`.
2. Set `DATABASE_URL` (the hosted connection string). Set `GEMINI_API_KEY` if you want AI (optional).
3. `STAFF_TOKEN` is generated for you. Open the service's **Environment** tab and copy it: it is the staff password
   you type into the app. Do not reuse the lab token from your `.env`.
4. Deploy. When it is live, open `https://<service>.onrender.com/api/health`: it should say `"status": "ok"`.
5. Open the site root. Staff screens ask for the staff token.

## 5. After the first deploy

* **Flood what-if needs elevation data.** Open City Simulation, the Flood tab, and use the download button (about a minute).
  The file is stored on the container's disk, so repeat it after a restart or redeploy.
* **Uploaded photos live on the container's disk** too. On a free instance they can disappear when it restarts or is
  redeployed. For a lasting deployment move uploads to object storage; that is not built.
* **Free instances sleep when idle** and take a while to wake up. Open the site a few minutes before presenting.
* Do not collect real citizen reports on a demo deployment. Photos and locations are personal data.

## If you only need to present

Running locally and sharing it through a tunnel avoids all of the above, for example
`cloudflared tunnel --url http://localhost:5173` while `uvicorn` and `npm run dev` run. Treat the public link as
temporary and keep the staff token private.
