"""Baseline: full UrbanTwin schema (phases 0-8).

Safe on both a brand-new database and one created by the earlier phases:
missing tables are created, and the few columns added since Phase 5 are added
with IF NOT EXISTS. Later schema changes get their own numbered revisions
(use `alembic revision --autogenerate -m "..."`).

Revision ID: 0001
Revises:
"""

from alembic import op

import app.models  # noqa: F401
from app.database import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(bind=bind, checkfirst=True)
    # Columns that did not exist when phases 0-5 created their tables.
    op.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE issues ADD COLUMN IF NOT EXISTS is_demo BOOLEAN NOT NULL DEFAULT false")
    for table in ("roads", "buildings", "water_bodies", "drains"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN osm_id TYPE BIGINT")


def downgrade() -> None:
    raise RuntimeError("The baseline cannot be downgraded. Drop the database instead.")
