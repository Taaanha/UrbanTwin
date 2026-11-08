from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    """An approved works project. Distinct from the intervention it came from."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    intervention_id: Mapped[int] = mapped_column(ForeignKey("interventions.id"), nullable=False, unique=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="approved", nullable=False)
    approved_budget_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    specification: Mapped[str] = mapped_column(Text, nullable=False)
    contractor_name: Mapped[str | None] = mapped_column(String(256))
    start_date: Mapped[date | None] = mapped_column(Date)
    planned_end_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), default="staff", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updates: Mapped[list["ProjectUpdate"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectUpdate.id"
    )
    inspections: Mapped[list["Inspection"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Inspection.id"
    )
    evidence: Mapped[list["ProjectEvidence"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectEvidence.id"
    )


class ProjectUpdate(Base):
    __tablename__ = "project_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    expenditure_bdt: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="updates")


class Inspection(Base):
    """An inspection record. 'independent' marks inspections not done by the delivery team."""

    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    inspector: Mapped[str] = mapped_column(String(128), nullable=False)
    independent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    condition_score: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="inspections")


class ProjectEvidence(Base):
    __tablename__ = "project_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    update_id: Mapped[int | None] = mapped_column(ForeignKey("project_updates.id"))
    inspection_id: Mapped[int | None] = mapped_column(ForeignKey("inspections.id"))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(128), nullable=False)
    original_name: Mapped[str] = mapped_column(String(256), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="evidence")
