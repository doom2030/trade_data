"""Orchestrate the daily kline update pipeline (shared by CLI and scheduler)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import CollectJob
from collector.baostock_client import BaostockClient
from collector.collect_lock import acquire_collect_lock, format_lock_contention_message
from collector.job_helper import append_job_log
from collector.kline_sync import (
    create_catchup_jobs,
    daily_update_klines,
    get_missed_trading_days,
    is_trading_day,
)
from collector.quality_check import run_quality_check
from collector.retry_service import retry_failed_items
from collector.stock_meta_sync import sync_stock_meta
from collector.trade_calendar_sync import ensure_trade_calendar_for_date

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class DailyUpdateResult:
    ok: bool
    skipped_lock: bool = False
    non_trading_day: bool = False
    job: CollectJob | None = None
    message: str = ""


def format_job_summary(job: CollectJob) -> str:
    return (
        f"Daily update job {job.id} status={job.status} "
        f"total={job.total_items} success={job.success_items} "
        f"failed={job.failed_items} skipped={job.skipped_items} "
        f"inserted={job.inserted_rows} updated={job.updated_rows}"
    )


def run_daily_update(trade_date: date | None = None) -> DailyUpdateResult:
    """Run calendar ensure, catchup enqueue, meta sync, day kline update, quality check."""
    target = trade_date or date.today()
    session = SessionLocal()
    client = BaostockClient()
    try:
        with acquire_collect_lock(session) as acquired:
            if not acquired:
                msg = format_lock_contention_message(session)
                logger.warning("daily_update skipped: %s", msg)
                return DailyUpdateResult(ok=False, skipped_lock=True, message=msg)

            ensure_trade_calendar_for_date(session, client, target)

            if not is_trading_day(session, target):
                job = daily_update_klines(session, client, target)
                append_job_log(
                    session,
                    job,
                    "日更跳过：非交易日",
                    payload=(job.params or {}).get("summary"),
                )
                session.commit()
                summary = format_job_summary(job)
                logger.info(summary)
                return DailyUpdateResult(
                    ok=True,
                    non_trading_day=True,
                    job=job,
                    message=summary,
                )

            retry_failed_items(
                session,
                client,
                settings.failed_job_max_attempts,
                settings.failed_job_retry_limit,
            )

            missed = get_missed_trading_days(session, target)
            if missed:
                job_ids = create_catchup_jobs(session, missed)
                logger.info(
                    "Created %s catchup jobs for %s missed days",
                    len(job_ids),
                    len(missed),
                )

            sync_stock_meta(session, client, target)

            job = daily_update_klines(session, client, target)
            run_quality_check(session, job.id)
            job = session.get(CollectJob, job.id)
            if job:
                append_job_log(
                    session,
                    job,
                    "日更汇总",
                    payload={
                        "trade_date": target.isoformat(),
                        "total_items": job.total_items,
                        "success_items": job.success_items,
                        "failed_items": job.failed_items,
                        "skipped_items": job.skipped_items,
                        "inserted_rows": job.inserted_rows,
                        "updated_rows": job.updated_rows,
                        "status": job.status,
                    },
                )
                session.commit()
                summary = format_job_summary(job)
                logger.info(summary)
                return DailyUpdateResult(ok=True, job=job, message=summary)

            return DailyUpdateResult(ok=False, message="daily_update job missing after run")
    finally:
        client.logout()
        session.close()
