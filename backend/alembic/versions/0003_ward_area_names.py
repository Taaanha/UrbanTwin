"""Rename the demonstration wards so each number carries its area names.

Only touches wards that still have the importer's default name, so a database
with official, hand-named wards is left alone.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

from app.geo_constants import ward_display_name

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The area-name labels are longer than the original 128-character column.
    op.alter_column("wards", "name", type_=sa.String(256), existing_type=sa.String(128), existing_nullable=False)
    conn = op.get_bind()
    for number in range(1, 10):
        conn.execute(
            text("UPDATE wards SET name = :new WHERE ward_number = :n AND name = :old"),
            {"new": ward_display_name(number), "n": number, "old": f"Ward {number} (demonstration grid)"},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for number in range(1, 10):
        conn.execute(
            text("UPDATE wards SET name = :old WHERE ward_number = :n AND name = :new"),
            {"new": ward_display_name(number), "n": number, "old": f"Ward {number} (demonstration grid)"},
        )
    # Names are short again here, so the column can go back to its original width.
    op.alter_column("wards", "name", type_=sa.String(128), existing_type=sa.String(256), existing_nullable=False)
