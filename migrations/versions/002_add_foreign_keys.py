"""add foreign key constraints

Revision ID: 002
Revises: 001
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_stock_status_history_symbol",
        "stock_status_history",
        "stock_master",
        ["symbol"],
        ["symbol"],
    )
    op.create_foreign_key(
        "fk_stock_industry_current_symbol",
        "stock_industry_current",
        "stock_master",
        ["symbol"],
        ["symbol"],
    )
    op.create_foreign_key(
        "fk_stock_suspension_symbol",
        "stock_suspension",
        "stock_master",
        ["symbol"],
        ["symbol"],
    )
    for table in ("kline_day",):
        op.create_foreign_key(
            f"fk_{table}_symbol",
            table,
            "stock_master",
            ["symbol"],
            ["symbol"],
        )
    op.create_foreign_key(
        "fk_collect_job_item_job_id",
        "collect_job_item",
        "collect_job",
        ["job_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_collect_job_item_symbol",
        "collect_job_item",
        "stock_master",
        ["symbol"],
        ["symbol"],
    )
    op.create_foreign_key(
        "fk_collect_job_retry_of_job_id",
        "collect_job",
        "collect_job",
        ["retry_of_job_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_collect_job_retry_of_item_id",
        "collect_job",
        "collect_job_item",
        ["retry_of_item_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_quality_check_result_job_id",
        "quality_check_result",
        "collect_job",
        ["job_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_quality_check_result_job_item_id",
        "quality_check_result",
        "collect_job_item",
        ["job_item_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_quality_check_result_symbol",
        "quality_check_result",
        "stock_master",
        ["symbol"],
        ["symbol"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_quality_check_result_symbol", "quality_check_result", type_="foreignkey")
    op.drop_constraint("fk_quality_check_result_job_item_id", "quality_check_result", type_="foreignkey")
    op.drop_constraint("fk_quality_check_result_job_id", "quality_check_result", type_="foreignkey")
    op.drop_constraint("fk_collect_job_retry_of_item_id", "collect_job", type_="foreignkey")
    op.drop_constraint("fk_collect_job_retry_of_job_id", "collect_job", type_="foreignkey")
    op.drop_constraint("fk_collect_job_item_symbol", "collect_job_item", type_="foreignkey")
    op.drop_constraint("fk_collect_job_item_job_id", "collect_job_item", type_="foreignkey")
    for table in ("kline_day",):
        op.drop_constraint(f"fk_{table}_symbol", table, type_="foreignkey")
    op.drop_constraint("fk_stock_suspension_symbol", "stock_suspension", type_="foreignkey")
    op.drop_constraint("fk_stock_industry_current_symbol", "stock_industry_current", type_="foreignkey")
    op.drop_constraint("fk_stock_status_history_symbol", "stock_status_history", type_="foreignkey")
