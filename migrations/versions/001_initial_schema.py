"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_master",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("board", sa.Text(), nullable=False),
        sa.Column("ipo_date", sa.Date(), nullable=True),
        sa.Column("out_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("security_type", sa.Text(), nullable=False, server_default="stock"),
        sa.Column("source", sa.Text(), nullable=False, server_default="baostock"),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol"),
        sa.UniqueConstraint("exchange", "code", name="uq_stock_master_exchange_code"),
    )
    op.create_index("idx_stock_master_board", "stock_master", ["board"])
    op.create_index("idx_stock_master_status", "stock_master", ["status"])

    op.create_table(
        "stock_status_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_stock_status_history_symbol", "stock_status_history", ["symbol", "valid_from", "valid_to"]
    )
    op.create_index(
        "idx_stock_status_history_status", "stock_status_history", ["status", "valid_from", "valid_to"]
    )

    op.create_table(
        "stock_industry_current",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("industry_name", sa.Text(), nullable=True),
        sa.Column("industry_code", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="baostock"),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol"),
    )
    op.create_index("idx_stock_industry_current_name", "stock_industry_current", ["industry_name"])
    op.create_index("idx_stock_industry_current_snapshot", "stock_industry_current", ["snapshot_date"])

    op.create_table(
        "trade_calendar",
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("is_trading_day", sa.Boolean(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="baostock"),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("trade_date"),
    )
    op.create_index("idx_trade_calendar_is_trading_day", "trade_calendar", ["is_trading_day", "trade_date"])

    op.create_table(
        "stock_suspension",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default="suspended"),
        sa.Column("source", sa.Text(), nullable=False, server_default="baostock_infer"),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "trade_date"),
    )
    op.create_index("idx_stock_suspension_trade_date", "stock_suspension", ["trade_date"])
    op.create_index("idx_stock_suspension_resolved", "stock_suspension", ["resolved_at"])

    kline_cols = [
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("adjust_flag", sa.Text(), nullable=False),
        sa.Column("open", sa.Numeric(18, 6), nullable=True),
        sa.Column("high", sa.Numeric(18, 6), nullable=True),
        sa.Column("low", sa.Numeric(18, 6), nullable=True),
        sa.Column("close", sa.Numeric(18, 6), nullable=True),
        sa.Column("preclose", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.Numeric(24, 4), nullable=True),
        sa.Column("amount", sa.Numeric(24, 4), nullable=True),
        sa.Column("turn", sa.Numeric(18, 8), nullable=True),
        sa.Column("pct_chg", sa.Numeric(18, 8), nullable=True),
        sa.Column("tradestatus", sa.Integer(), nullable=True),
        sa.Column("is_st", sa.Boolean(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="baostock"),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]

    for table_name in ("kline_day", "kline_week", "kline_month"):
        op.create_table(
            table_name,
            *kline_cols,
            sa.PrimaryKeyConstraint("symbol", "trade_date", "adjust_flag"),
        )
        op.create_index(f"idx_{table_name}_symbol_date", table_name, ["symbol", "trade_date"])
        op.create_index(f"idx_{table_name}_trade_date", table_name, ["trade_date"])
        op.create_index(f"idx_{table_name}_adjust", table_name, ["adjust_flag"])

    op.create_table(
        "collect_job",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("frequency", sa.Text(), nullable=True),
        sa.Column("adjust_flag", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("target_trade_date", sa.Date(), nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exhausted_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("compensated_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_of_job_id", sa.BigInteger(), nullable=True),
        sa.Column("retry_of_item_id", sa.BigInteger(), nullable=True),
        sa.Column("params", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_collect_job_type_status", "collect_job", ["job_type", "status"])
    op.create_index("idx_collect_job_frequency", "collect_job", ["frequency"])
    op.create_index("idx_collect_job_created_at", "collect_job", ["created_at"])
    op.create_index("idx_collect_job_retry_of_item", "collect_job", ["retry_of_item_id"])

    op.create_table(
        "collect_job_item",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=True),
        sa.Column("frequency", sa.Text(), nullable=True),
        sa.Column("adjust_flag", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("params", postgresql.JSONB(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_collect_job_item_job_id", "collect_job_item", ["job_id"])
    op.create_index("idx_collect_job_item_status", "collect_job_item", ["status"])
    op.create_index(
        "idx_collect_job_item_retry_lookup",
        "collect_job_item",
        ["status", "frequency", "adjust_flag", "symbol", "start_date", "end_date"],
    )

    op.create_table(
        "quality_check_result",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.BigInteger(), nullable=True),
        sa.Column("job_item_id", sa.BigInteger(), nullable=True),
        sa.Column("symbol", sa.Text(), nullable=True),
        sa.Column("frequency", sa.Text(), nullable=True),
        sa.Column("adjust_flag", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("check_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("sample_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_quality_check_result_job", "quality_check_result", ["job_id", "job_item_id"])
    op.create_index(
        "idx_quality_check_result_symbol",
        "quality_check_result",
        ["symbol", "frequency", "adjust_flag", "start_date", "end_date"],
    )
    op.create_index(
        "idx_quality_check_result_status", "quality_check_result", ["status", "severity", "check_type"]
    )


def downgrade() -> None:
    op.drop_table("quality_check_result")
    op.drop_table("collect_job_item")
    op.drop_table("collect_job")
    for table_name in ("kline_month", "kline_week", "kline_day"):
        op.drop_table(table_name)
    op.drop_table("stock_suspension")
    op.drop_table("trade_calendar")
    op.drop_table("stock_industry_current")
    op.drop_table("stock_status_history")
    op.drop_table("stock_master")
