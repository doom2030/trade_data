"""add industry board tables (Tonghuashun / Shenwan)

Revision ID: 003
Revises: 002
Create Date: 2026-07-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "industry_board",
        sa.Column("board_code", sa.Text(), primary_key=True),
        sa.Column("board_name", sa.Text(), nullable=False),
        sa.Column("pinyin_initial", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="ths"),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_industry_board_name", "industry_board", ["board_name"])
    op.create_index("idx_industry_board_pinyin", "industry_board", ["pinyin_initial"])

    op.create_table(
        "stock_industry_board",
        sa.Column("symbol", sa.Text(), sa.ForeignKey("stock_master.symbol"), primary_key=True),
        sa.Column("board_code", sa.Text(), sa.ForeignKey("industry_board.board_code"), nullable=False),
        sa.Column("board_name", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="ths"),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_stock_industry_board_code", "stock_industry_board", ["board_code"])
    op.create_index("idx_stock_industry_board_name", "stock_industry_board", ["board_name"])


def downgrade() -> None:
    op.drop_index("idx_stock_industry_board_name", table_name="stock_industry_board")
    op.drop_index("idx_stock_industry_board_code", table_name="stock_industry_board")
    op.drop_table("stock_industry_board")
    op.drop_index("idx_industry_board_pinyin", table_name="industry_board")
    op.drop_index("idx_industry_board_name", table_name="industry_board")
    op.drop_table("industry_board")
