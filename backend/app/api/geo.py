from typing import Any

from fastapi import APIRouter, Depends
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.geo import (
    AdminBoundary,
    Building,
    DataSource,
    Drain,
    Road,
    StudyArea,
    Ward,
    WaterBody,
)

router = APIRouter(prefix="/api/geo", tags=["geo"])


def _feature(geom, properties: dict[str, Any]) -> dict[str, Any]:
    shape = to_shape(geom)
    return {
        "type": "Feature",
        "geometry": mapping(shape),
        "properties": properties,
    }


def _collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(DataSource).order_by(DataSource.layer)).all()
    return [
        {
            "layer": row.layer,
            "source_name": row.source_name,
            "license": row.license,
            "crs": row.crs,
            "acquired_at": row.acquired_at.isoformat() if row.acquired_at else None,
            "limitations": row.limitations,
            "processing_steps": row.processing_steps,
            "is_demo": row.is_demo,
        }
        for row in rows
    ]


@router.get("/summary")
def layer_summary(db: Session = Depends(get_db)) -> dict[str, int]:
    counts = {
        "study_areas": db.scalar(select(func.count()).select_from(StudyArea)) or 0,
        "admin_boundaries": db.scalar(select(func.count()).select_from(AdminBoundary)) or 0,
        "wards": db.scalar(select(func.count()).select_from(Ward)) or 0,
        "roads": db.scalar(select(func.count()).select_from(Road)) or 0,
        "buildings": db.scalar(select(func.count()).select_from(Building)) or 0,
        "water_bodies": db.scalar(select(func.count()).select_from(WaterBody)) or 0,
        "drains": db.scalar(select(func.count()).select_from(Drain)) or 0,
    }
    return counts


@router.get("/study-area")
def study_area(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(StudyArea)).all()
    return _collection(
        [
            _feature(
                row.geom,
                {"name": row.name, "is_demo": row.is_demo, "notes": row.notes},
            )
            for row in rows
        ]
    )


@router.get("/admin-boundaries")
def admin_boundaries(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(AdminBoundary)).all()
    return _collection(
        [
            _feature(
                row.geom,
                {
                    "name": row.name,
                    "admin_level": row.admin_level,
                    "osm_id": row.osm_id,
                    "is_demo": row.is_demo,
                    "source": row.source,
                },
            )
            for row in rows
        ]
    )


@router.get("/wards")
def wards(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(Ward).order_by(Ward.ward_number)).all()
    return _collection(
        [
            _feature(
                row.geom,
                {
                    "name": row.name,
                    "ward_number": row.ward_number,
                    "is_demo": row.is_demo,
                    "notes": row.notes,
                },
            )
            for row in rows
        ]
    )


@router.get("/roads")
def roads(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(Road)).all()
    return _collection(
        [
            _feature(
                row.geom,
                {
                    "name": row.name,
                    "highway": row.highway,
                    "osm_id": row.osm_id,
                    "is_demo": row.is_demo,
                },
            )
            for row in rows
        ]
    )


@router.get("/buildings")
def buildings(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(Building)).all()
    return _collection(
        [
            _feature(
                row.geom,
                {"name": row.name, "osm_id": row.osm_id, "is_demo": row.is_demo},
            )
            for row in rows
        ]
    )


@router.get("/water")
def water(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(WaterBody)).all()
    return _collection(
        [
            _feature(
                row.geom,
                {
                    "name": row.name,
                    "waterway": row.waterway,
                    "osm_id": row.osm_id,
                    "is_demo": row.is_demo,
                },
            )
            for row in rows
        ]
    )


@router.get("/drains")
def drains(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.scalars(select(Drain)).all()
    return _collection(
        [
            _feature(
                row.geom,
                {
                    "name": row.name,
                    "waterway": row.waterway,
                    "osm_id": row.osm_id,
                    "is_demo": row.is_demo,
                },
            )
            for row in rows
        ]
    )
