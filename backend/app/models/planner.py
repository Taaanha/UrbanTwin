from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UnitRate(Base):
    """Editable lab placeholder rate. Never an official municipal schedule."""

    __tablename__ = "unit_rates"
    __table_args__ = (UniqueConstraint("action_code", "category", name="uq_unit_rate_action_category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_code: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="BDT", nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Intervention(Base):
    """A recommended treatment for a verified issue. Not an approved project."""

    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), nullable=False, index=True)
    action_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    assumptions: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    estimates: Mapped[list["CostEstimate"]] = relationship(back_populates="intervention")


class CostEstimate(Base):
    __tablename__ = "cost_estimates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intervention_id: Mapped[int] = mapped_column(ForeignKey("interventions.id"), nullable=False, index=True)
    labour_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    materials_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    equipment_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    contingency_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    total_low_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    total_mid_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    total_high_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    is_indicative: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assumptions: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    intervention: Mapped[Intervention] = relationship(back_populates="estimates")


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    budget_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    spent_bdt: Mapped[float] = mapped_column(Float, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(32), default="compare", nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["PlanItem"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class PlanItem(Base):
    __tablename__ = "plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), nullable=False, index=True)
    intervention_id: Mapped[int] = mapped_column(ForeignKey("interventions.id"), nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score_used: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_mid_bdt: Mapped[float] = mapped_column(Float, nullable=False)

    plan: Mapped[Plan] = relationship(back_populates="items")
