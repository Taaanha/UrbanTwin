# UrbanTwin architecture

A **modular monolith**: one FastAPI service, one PostgreSQL/PostGIS database, one React app. No microservices, no paid APIs. Each module is a router (`app/api`), a service with the logic (`app/services`), and tables (`app/models`).

## System diagram

```mermaid
flowchart LR
  subgraph Browser
    CP[Citizen portal<br/>/ and /track]
    GD[Government dashboard<br/>/overview /dashboard /investigator ...]
  end
  subgraph FastAPI["FastAPI backend (app/)"]
    AUTH[auth.py<br/>X-Staff-Token]
    M1[reports + geo<br/>City Monitor]
    M2[investigator<br/>duplicates.py]
    M3[intelligence<br/>spatial links, graph]
    M4[planner<br/>costs, OR-Tools]
    M5[accountability<br/>projects, screening]
    M6[simulation<br/>green + budget]
    AUD[audit service]
  end
  DB[(PostgreSQL + PostGIS)]
  FS[(uploads folder)]
  OSM[(OpenStreetMap<br/>import scripts)]
  CP -->|public| M1
  GD -->|token| AUTH --> M2 & M3 & M4 & M5 & M6
  M1 & M2 & M3 & M4 & M5 & M6 --> DB
  M1 & M5 --> FS
  M2 & M4 & M5 --> AUD --> DB
  OSM -. scripts/import_osm_*.py .-> DB
```

## How the modules talk to each other

They share the database, and each stage references the previous one by foreign key:

```
Report (citizen)
  -> Verification (human decision, kept as history)
     -> Issue (verified)                      [Investigator creates]
        -> IssueAsset / IssueRelation          [Intelligence links road, drain, ward, recurrence]
        -> Intervention + CostEstimate         [Planner proposes and prices]
           -> Project (approved works)         [Accountability]
              -> ProjectUpdate / Inspection / ProjectEvidence
              -> later Issue near the same spot -> recurrence screen
Scenario (Simulation) reads wards, buildings, green spaces and the planner's candidates
AuditLog records every consequential staff action
```

Concrete hand-offs in code:
* `investigator.verify` calls `intelligence.refresh_all` and `accountability.recurrences_for_new_issue` (a new issue near a completed project is reported straight away).
* `planner.generate_interventions` uses intelligence relations (`possible_recurrence`, `same_road`) in the priority score.
* `accountability.complete` sets the issue to `repair_reported`; an independent passing inspection sets `resolved_verified`.
* `simulation` budget scenarios reuse the planner's candidates and methods; green scenarios price planting from the planner's `tree_planting` rate.

## Database (ER diagram)

```mermaid
erDiagram
  reports ||--o{ evidence_files : has
  reports ||--o{ verifications : "decided on"
  reports ||--o| issue_reports : "linked by"
  issues ||--o{ issue_reports : has
  issues ||--o{ verifications : "related issue"
  issues ||--o{ issue_assets : "snapped to"
  issues ||--o{ issue_relations : from
  issues ||--o{ issue_relations : to
  issues ||--o{ interventions : "treated by"
  interventions ||--o{ cost_estimates : priced
  interventions ||--o{ plan_items : "considered in"
  plans ||--o{ plan_items : has
  interventions ||--o| projects : "approved as"
  issues ||--o{ projects : "repaired by"
  projects ||--o{ project_updates : progress
  projects ||--o{ inspections : inspected
  projects ||--o{ project_evidence : files
  unit_rates }o..o{ interventions : "priced from"
  wards ||..o{ issue_assets : "ward link"
  roads ||..o{ issue_assets : "road link"
  drains ||..o{ issue_assets : "drain link"
  water_bodies ||..o{ issue_assets : "water link"
  green_spaces }o..o{ scenarios : "read by"
  audit_logs }o..o{ projects : "records actions on"
```

Reference geography (no foreign keys, spatial joins only): `study_areas`, `admin_boundaries`, `wards`, `roads`, `buildings`, `water_bodies`, `drains`, `green_spaces`, plus the `data_sources` register (source, licence, CRS, processing, limitations).

Every geometry column is EPSG:4326 with a GiST spatial index. Report/issue/project/drain/green rows carry `is_demo`.

## Why PostgreSQL + PostGIS

Geometry types, spatial indexes and distance functions (`ST_DistanceSphere`, `ST_Contains`) are needed to snap issues to roads/wards. Relational integrity keeps the report -> issue -> project chain consistent, and JSONB stores verification reasons and scenario results.

## API map

| Prefix | Access | Purpose |
|--------|--------|---------|
| `/api/health` | public | API + PostGIS check, shows whether staff login is on |
| `/api/geo/*` | public | OSM layers, demo wards, study area as GeoJSON |
| `/api/reports` (POST), `/api/reports/track/{id}`, `/api/reports/meta` | public | citizen submit and track |
| `/api/reports` (GET), `/geojson`, `PATCH .../status` | staff | monitoring |
| `/api/investigator/*` | staff | queue, inspect, verify, issues |
| `/api/intelligence/*` | staff | refresh, issue links, recurrence, graph, geojson |
| `/api/planner/*` | staff | rates, interventions, compare |
| `/api/accountability/*` | staff | projects, updates, completion, inspections, recurrence, geojson |
| `/api/simulation/*` | staff | green baseline/scenarios, budget scenarios |
| `/api/overview`, `/api/audit`, `/api/data-sources` | staff | live counts, audit trail, dataset register |

## Frontend pages

`/` citizen report (English/Bangla) · `/track` · `/overview` · `/dashboard` (map, filters, status) · `/investigator` · `/intelligence` · `/planner` · `/accountability` · `/simulation` · `/admin`.

## Testing strategy

* `backend/tests/` (pytest, 29 tests): unit tests for scoring, API tests through `TestClient`, a security test per staff route, lifecycle tests for projects, scenario determinism, and a test that the demo seed is fully labelled.
* Isolated `*_test` database, temp upload folder.
* `npm run build` runs the TypeScript type-check.
* Not covered by automated tests: browser interaction and map rendering (check by hand with `docs/DEMO_SCRIPT.md`).

## Migrations

`alembic upgrade head`. `0001_baseline` creates missing tables and adds columns introduced after Phase 5, so it works on new and existing databases. Future changes: `alembic revision --autogenerate -m "..."`.
