"""add collect job logs

Revision ID: 004
Revises: 003
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collect_job_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.BigInteger(), sa.ForeignKey("collect_job.id"), nullable=False),
        sa.Column("level", sa.Text(), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_collect_job_log_job_id", "collect_job_log", ["job_id", "id"])
    op.create_index("idx_collect_job_log_created_at", "collect_job_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_collect_job_log_created_at", table_name="collect_job_log")
    op.drop_index("idx_collect_job_log_job_id", table_name="collect_job_log")
    op.drop_table("collect_job_log")
