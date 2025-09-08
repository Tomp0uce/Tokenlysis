from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_add_category_columns"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("coins", sa.Column("category_names", sa.Text(), nullable=True))
    op.add_column("coins", sa.Column("category_ids", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("coins", "category_ids")
    op.drop_column("coins", "category_names")
