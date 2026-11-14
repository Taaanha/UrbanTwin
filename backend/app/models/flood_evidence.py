from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FloodEvidence(Base):
    """One row of the flood evidence register: a reported event, a weather note, or a pointer to a dataset.

    This is a catalogue, not a map layer. Coordinates are stored only when the source supplied them, and
    nothing here is an observed flood extent.
    """

    __tablename__ = "flood_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    record_type: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date)
    publication_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_type: Mapped[str | None] = mapped_column(String(64))
    source_name: Mapped[str | None] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    coordinate_status: Mapped[str | None] = mapped_column(String(64))
    verification_status: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
