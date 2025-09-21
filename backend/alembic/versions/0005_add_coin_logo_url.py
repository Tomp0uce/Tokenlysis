"""Add logo_url column to coins."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_add_coin_logo_url"
down_revision = "0004_add_fear_greed_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "coins",
        sa.Column("logo_url", sa.String(), nullable=True, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("coins", "logo_url")
