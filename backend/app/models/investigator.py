from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Issue(Base):
    """A human-verified canonical problem. Distinct from a citizen report."""

    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    geom = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    links: Mapped[list["IssueReport"]] = relationship(back_populates="issue")


class IssueReport(Base):
    __tablename__ = "issue_reports"
    __table_args__ = (UniqueConstraint("report_id", name="uq_issue_reports_report_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), default="linked")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    issue: Mapped[Issue] = relationship(back_populates="links")


class Verification(Base):
    """Human decision. Original reports are never deleted or merged."""

    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    related_report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"))
    related_issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id"))
    score: Mapped[int | None] = mapped_column(Integer)
    reasons: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str] = mapped_column(String(64), default="lab-officer")
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
