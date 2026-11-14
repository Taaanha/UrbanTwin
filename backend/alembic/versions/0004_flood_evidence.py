"""Flood evidence register (catalogue of reports and data sources).

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flood_evidence",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("record_id", sa.String(32), nullable=False),
        sa.Column("record_type", sa.String(48), nullable=False),
        sa.Column("event_date", sa.Date),
        sa.Column("publication_date", sa.Date),
        sa.Column("location", sa.Text),
        sa.Column("district", sa.String(128)),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("evidence_type", sa.String(64)),
        sa.Column("source_name", sa.String(160)),
        sa.Column("source_url", sa.Text),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        sa.Column("coordinate_status", sa.String(64)),
        sa.Column("verification_status", sa.String(64)),
        sa.Column("notes", sa.Text),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_flood_evidence_record_id", "flood_evidence", ["record_id"], unique=True)
    op.create_index("ix_flood_evidence_record_type", "flood_evidence", ["record_type"])


def downgrade() -> None:
    op.drop_index("ix_flood_evidence_record_type", table_name="flood_evidence")
    op.drop_index("ix_flood_evidence_record_id", table_name="flood_evidence")
    op.drop_table("flood_evidence")
