from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IssueAsset(Base):
    """Spatial link from a verified issue to OSM or demo GIS, not a causal claim."""

    __tablename__ = "issue_assets"
    __table_args__ = (UniqueConstraint("issue_id", "asset_kind", "asset_id", name="uq_issue_asset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), nullable=False, index=True)
    asset_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_id: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_name: Mapped[str | None] = mapped_column(String(256))
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    snap_lon: Mapped[float | None] = mapped_column(Float)
    snap_lat: Mapped[float | None] = mapped_column(Float)
    generated_by: Mapped[str] = mapped_column(String(32), default="spatial", nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IssueRelation(Base):
    """Nearby / same-asset / possible-recurrence links between verified issues."""

    __tablename__ = "issue_relations"
    __table_args__ = (
        UniqueConstraint("from_issue_id", "to_issue_id", "relation_type", name="uq_issue_relation"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), nullable=False, index=True)
    to_issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    days_apart: Mapped[float | None] = mapped_column(Float)
    generated_by: Mapped[str] = mapped_column(String(32), default="spatial", nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
