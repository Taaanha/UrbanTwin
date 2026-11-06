from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import check_database

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="AI-powered urban intelligence platform for Noakhali Paurashava",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    """Used by the frontend and lab demo to prove API + PostGIS are connected."""
    try:
        database_info = check_database()
        return {
            "status": "ok",
            "service": "urbantwin-backend",
            **database_info,
        }
    except SQLAlchemyError as exc:
        return {
            "status": "degraded",
            "service": "urbantwin-backend",
            "database": "error",
            "detail": str(exc.__cause__ or exc),
        }
