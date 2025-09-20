from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_add_fdv_and_pct_changes"
down_revision = "0002_add_category_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "latest_prices",
        sa.Column("fully_diluted_market_cap", sa.Float(), nullable=True),
    )
    op.add_column(
        "latest_prices",
        sa.Column("pct_change_7d", sa.Float(), nullable=True),
    )
    op.add_column(
        "latest_prices",
        sa.Column("pct_change_30d", sa.Float(), nullable=True),
    )
    op.add_column(
        "prices",
        sa.Column("fully_diluted_market_cap", sa.Float(), nullable=True),
    )
    op.add_column(
        "prices",
        sa.Column("pct_change_7d", sa.Float(), nullable=True),
    )
    op.add_column(
        "prices",
        sa.Column("pct_change_30d", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prices", "pct_change_30d")
    op.drop_column("prices", "pct_change_7d")
    op.drop_column("prices", "fully_diluted_market_cap")
    op.drop_column("latest_prices", "pct_change_30d")
    op.drop_column("latest_prices", "pct_change_7d")
    op.drop_column("latest_prices", "fully_diluted_market_cap")
