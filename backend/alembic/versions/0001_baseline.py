"""baseline schema"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coins",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("categories", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "latest_prices",
        sa.Column("coin_id", sa.String(), primary_key=True),
        sa.Column("vs_currency", sa.String(), primary_key=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("volume_24h", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("pct_change_24h", sa.Float(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_latest_prices_rank", "latest_prices", ["rank"])

    op.create_table(
        "prices",
        sa.Column("coin_id", sa.String(), primary_key=True),
        sa.Column("vs_currency", sa.String(), primary_key=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("volume_24h", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("pct_change_24h", sa.Float(), nullable=True),
    )
    op.create_index("ix_prices_snapshot_at", "prices", ["snapshot_at"])
    op.create_index("ix_prices_coin_snapshot_at", "prices", ["coin_id", "snapshot_at"])

    op.create_table(
        "meta",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("meta")
    op.drop_index("ix_prices_coin_snapshot_at", table_name="prices")
    op.drop_index("ix_prices_snapshot_at", table_name="prices")
    op.drop_table("prices")
    op.drop_index("ix_latest_prices_rank", table_name="latest_prices")
    op.drop_table("latest_prices")
    op.drop_table("coins")
