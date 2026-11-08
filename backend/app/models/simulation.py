from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GreenSpace(Base):
    """Parks, grass, woods and similar polygons. Real (OSM) or labelled demo."""

    __tablename__ = "green_spaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    osm_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    geom = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)


class Scenario(Base):
    """A saved what-if run: inputs, outputs and the assumptions behind them."""

    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    assumptions: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), default="staff", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
