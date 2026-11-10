"""Reports get an optional free-text location (landmark or address) written by the citizen.

Safe to run on a database whose baseline already created the column.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS location_text VARCHAR(200)")


def downgrade() -> None:
    op.execute("ALTER TABLE reports DROP COLUMN IF EXISTS location_text")
