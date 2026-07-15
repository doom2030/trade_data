from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.migrations import expected_migration_head

router = APIRouter()

REQUIRED_TABLES = (
    "alembic_version",
    "stock_master",
    "collect_job",
    "collect_job_item",
    "collect_job_log",
    "trade_calendar",
    "industry_board",
    "stock_industry_board",
)


def _schema_ready(db: Session) -> bool:
    for table in REQUIRED_TABLES:
        exists = db.scalar(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = :name"
                ")"
            ),
            {"name": table},
        )
        if not exists:
            return False
    return True


def _migration_status(db: Session) -> tuple[str, str | None, str | None]:
    try:
        expected = expected_migration_head()
    except Exception:
        return "error", None, None

    if not expected:
        return "unknown", None, None

    try:
        current = db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    except Exception:
        return "error", None, expected

    if current is None:
        return "missing", None, expected
    if current == expected:
        return "ok", current, expected
    return "behind", current, expected


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        return {"status": "degraded", "database": "error", "schema": "unknown", "migration": "unknown"}

    try:
        schema_status = "ok" if _schema_ready(db) else "missing_tables"
    except Exception:
        schema_status = "error"

    migration_status, migration_current, migration_expected = _migration_status(db)

    overall = (
        "ok"
        if db_status == "ok" and schema_status == "ok" and migration_status == "ok"
        else "degraded"
    )
    payload = {
        "status": overall,
        "database": db_status,
        "schema": schema_status,
        "migration": migration_status,
    }
    if migration_current is not None:
        payload["migration_current"] = migration_current
    if migration_expected is not None:
        payload["migration_expected"] = migration_expected
    return payload
