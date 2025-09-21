"""Add fear_greed_index table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_add_fear_greed_index"
down_revision = "0003_add_fdv_and_pct_changes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fear_greed_index",
        sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_fear_greed_timestamp",
        "fear_greed_index",
        ["timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_fear_greed_timestamp", table_name="fear_greed_index")
    op.drop_table("fear_greed_index")
