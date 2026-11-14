from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api.accountability import router as accountability_router
from app.api.advisor import router as advisor_router
from app.api.flood_evidence import router as flood_evidence_router
from app.api.geo import router as geo_router
from app.api.insights import router as insights_router
from app.api.intelligence import router as intelligence_router
from app.api.investigator import router as investigator_router
from app.api.planner import router as planner_router
from app.api.overview import router as overview_router
from app.api.reports import router as reports_router
from app.api.simulation import router as simulation_router
from app.auth import auth_enabled
from app.config import get_settings
from app.database import check_database, init_db
from app.spa import mount_frontend

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.auto_create_tables:
        init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="AI-powered urban intelligence platform for Noakhali Paurashava",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(geo_router)
app.include_router(reports_router)
app.include_router(investigator_router)
app.include_router(intelligence_router)
app.include_router(planner_router)
app.include_router(accountability_router)
app.include_router(overview_router)
app.include_router(simulation_router)
app.include_router(insights_router)
app.include_router(advisor_router)
app.include_router(flood_evidence_router)


@app.get("/api/health")
def health_check():
    """Used by the frontend and lab demo to prove API + PostGIS are connected."""
    try:
        database_info = check_database()
        return {
            "status": "ok",
            "service": "urbantwin-backend",
            "staff_auth": "enabled" if auth_enabled() else "DISABLED (lab mode)",
            **database_info,
        }
    except SQLAlchemyError as exc:
        return {
            "status": "degraded",
            "service": "urbantwin-backend",
            "database": "error",
            "detail": str(exc.__cause__ or exc),
        }


# Last on purpose: the catch-all must come after every API route.
mount_frontend(app, settings.frontend_dist)
