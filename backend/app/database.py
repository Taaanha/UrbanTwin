from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def check_database() -> dict[str, str]:
    """Run a live query so /api/health proves PostgreSQL and PostGIS work."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        postgis_version = connection.execute(text("SELECT PostGIS_Version()")).scalar_one()
    return {"database": "connected", "postgis": str(postgis_version)}
