"""add stock favorites

Revision ID: 005
Revises: 004
Create Date: 2026-07-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_favorite",
        sa.Column("symbol", sa.Text(), sa.ForeignKey("stock_master.symbol"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol"),
    )
    op.create_index("idx_stock_favorite_created_at", "stock_favorite", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_stock_favorite_created_at", table_name="stock_favorite")
    op.drop_table("stock_favorite")
