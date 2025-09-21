"""Add social_links column to coins."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_add_coin_social_links"
down_revision = "0005_add_coin_logo_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "coins",
        sa.Column("social_links", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("coins", "social_links")
