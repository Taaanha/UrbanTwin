from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    layer: Mapped[str] = mapped_column(String(64), nullable=False)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    license: Mapped[str] = mapped_column(String(128), nullable=False)
    crs: Mapped[str] = mapped_column(String(32), nullable=False, default="EPSG:4326")
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    limitations: Mapped[str] = mapped_column(Text, nullable=False)
    processing_steps: Mapped[str] = mapped_column(Text, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class StudyArea(Base):
    __tablename__ = "study_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    geom = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)


class AdminBoundary(Base):
    __tablename__ = "admin_boundaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    admin_level: Mapped[str | None] = mapped_column(String(8))
    osm_id: Mapped[int | None] = mapped_column(BigInteger)
    geom = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="OpenStreetMap")


class Ward(Base):
    __tablename__ = "wards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ward_number: Mapped[int] = mapped_column(Integer, nullable=False)
    geom = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)


class Road(Base):
    __tablename__ = "roads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    highway: Mapped[str | None] = mapped_column(String(64))
    osm_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    geom = mapped_column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    osm_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    geom = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class WaterBody(Base):
    __tablename__ = "water_bodies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    waterway: Mapped[str | None] = mapped_column(String(64))
    osm_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    geom = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Drain(Base):
    __tablename__ = "drains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    waterway: Mapped[str | None] = mapped_column(String(64))
    osm_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    geom = mapped_column(Geometry(geometry_type="LINESTRING", srid=4326), nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
