import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import StockIndustryCurrent, StockMaster
from collector.baostock_client import BaostockClient
from collector.job_helper import create_job, finalize_job

logger = logging.getLogger(__name__)


def sync_industry(session: Session, client: BaostockClient, snapshot_date: date) -> int:
    job = create_job(session, "sync_industry", params={"snapshot_date": str(snapshot_date)})
    session.commit()

    try:
        rows = client.query_industry(snapshot_date)
        active_symbols = set(
            session.scalars(select(StockMaster.symbol).where(StockMaster.status == "active")).all()
        )
        upserted = 0
        for row in rows:
            symbol = row.get("code")
            if not symbol or symbol not in active_symbols:
                continue
            stmt = insert(StockIndustryCurrent).values(
                symbol=symbol,
                industry_name=row.get("industry"),
                industry_code=row.get("industryClassification"),
                snapshot_date=snapshot_date,
                source="baostock",
                raw_payload=row.get("raw_payload"),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol"],
                set_={
                    "industry_name": row.get("industry"),
                    "industry_code": row.get("industryClassification"),
                    "snapshot_date": snapshot_date,
                    "raw_payload": row.get("raw_payload"),
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            session.execute(stmt)
            upserted += 1

        job.inserted_rows = upserted
        finalize_job(session, job)
        session.commit()
        return upserted
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.finished_at = datetime.now(timezone.utc)
        session.commit()
        raise
