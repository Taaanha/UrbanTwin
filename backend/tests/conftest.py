"""Test isolation.

Tests NEVER touch your development database. They use `<dev database>_test`
(or TEST_DATABASE_URL), build the schema with create_all, seed a tiny labelled
geography, empty the report-side tables between tests and write uploads to a
temp folder. The database name must end in `_test` or the run aborts.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import dotenv_values  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402


def _test_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = os.environ.get("DATABASE_URL") or dotenv_values(BACKEND_DIR / ".env").get("DATABASE_URL")
    if not base:
        raise RuntimeError("Set DATABASE_URL in backend/.env or TEST_DATABASE_URL for tests.")
    url = make_url(base)
    name = url.database or "urbantwin"
    return url.set(database=name if name.endswith("_test") else f"{name}_test").render_as_string(hide_password=False)


TEST_URL = _test_url()
assert make_url(TEST_URL).database.endswith("_test"), "Refusing to run tests on a non-test database."
os.environ["DATABASE_URL"] = TEST_URL
os.environ["STAFF_TOKEN"] = ""
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="urbantwin_test_uploads_")


def _ensure_database() -> None:
    url = make_url(TEST_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    own = create_engine(url, isolation_level="AUTOCOMMIT")
    with own.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    own.dispose()


_ensure_database()

import pytest  # noqa: E402
from geoalchemy2.shape import from_shape  # noqa: E402
from shapely.geometry import LineString, Polygon, box  # noqa: E402

import app.models  # noqa: E402,F401
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.geo_constants import STUDY_BBOX  # noqa: E402
from app.models.geo import Road, StudyArea, Ward, WaterBody  # noqa: E402

GEO_TABLES = {
    "study_areas",
    "admin_boundaries",
    "wards",
    "roads",
    "buildings",
    "water_bodies",
    "drains",
    "green_spaces",
    "data_sources",
}


def _seed_geo() -> None:
    west, south, east, north = STUDY_BBOX
    with SessionLocal() as db:
        db.add(
            StudyArea(
                name="Test study area",
                geom=from_shape(box(west, south, east, north), srid=4326),
                is_demo=False,
                notes="Test envelope. Not an official boundary.",
            )
        )
        width, height = (east - west) / 3, (north - south) / 3
        number = 1
        for row in range(3):
            for col in range(3):
                cell = box(west + col * width, north - (row + 1) * height, west + (col + 1) * width, north - row * height)
                db.add(
                    Ward(
                        name=f"Ward {number} (demonstration grid)",
                        ward_number=number,
                        geom=from_shape(cell, srid=4326),
                        is_demo=True,
                        notes="Demonstration cell, not an official ward.",
                    )
                )
                number += 1
        db.add(
            Road(
                name="Station Road (test)",
                highway="residential",
                osm_id=1,
                geom=from_shape(LineString([(91.094, 22.8692), (91.104, 22.8692)]), srid=4326),
                properties={},
            )
        )
        db.add(
            Road(
                name="Court Road (test)",
                highway="tertiary",
                osm_id=2,
                geom=from_shape(LineString([(91.0995, 22.860), (91.0995, 22.880)]), srid=4326),
                properties={},
            )
        )
        db.add(
            WaterBody(
                name="Test pond",
                waterway=None,
                osm_id=3,
                geom=from_shape(Polygon([(91.110, 22.855), (91.111, 22.855), (91.111, 22.856), (91.110, 22.856)]), srid=4326),
                properties={},
            )
        )
        db.commit()


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _seed_geo()
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_state():
    tables = [t.name for t in Base.metadata.sorted_tables if t.name not in GEO_TABLES]
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE"))
        conn.execute(text("DELETE FROM drains"))
        conn.execute(text("DELETE FROM buildings"))
        conn.execute(text("DELETE FROM green_spaces"))
    yield


@pytest.fixture()
def staff_auth(monkeypatch):
    """Turns the staff gate on for one test."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "staff_token", "test-token")
    return {"X-Staff-Token": "test-token", "X-Staff-Name": "tester"}
