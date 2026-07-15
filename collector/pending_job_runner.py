import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import CollectJob, CollectJobItem
from collector.baostock_client import BaostockClient
from collector.collect_lock import acquire_collect_lock, format_lock_contention_message
from collector.industry_board_sync import sync_industry_boards
from collector.industry_sync import sync_industry
from collector.job_helper import finalize_job, mark_stale_running_jobs
from collector.kline_sync import collect_kline_item, daily_update_klines, run_catchup_job, update_weekly_monthly
from collector.quality_check import run_quality_check
from collector.retry_service import apply_retry_outcome, max_attempts_for_item, retry_failed_items
from collector.stock_meta_sync import sync_stock_meta
from collector.trade_calendar_sync import ensure_trade_calendar_for_date, sync_trade_calendar

logger = logging.getLogger(__name__)
settings = get_settings()

PENDING_JOB_TYPES = {
    "sync_stock_meta",
    "sync_industry",
    "sync_industry_boards",
    "sync_trade_calendar",
    "daily_update",
    "update_weekly",
    "update_monthly",
    "retry_failed_jobs",
    "quality_check",
    "manual_retry_failed_job",
    "manual_retry_failed_item",
    "manual_backfill_range",
    "catchup_daily_update",
}


def claim_pending_jobs(session: Session, limit: int) -> list[int]:
    """Atomically claim pending jobs using row-level locks."""
    mark_stale_running_jobs(session, settings.pending_job_stale_minutes)

    jobs = session.scalars(
        select(CollectJob)
        .where(
            CollectJob.status == "pending",
            CollectJob.job_type.in_(PENDING_JOB_TYPES),
        )
        .order_by(CollectJob.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()

    now = datetime.now(timezone.utc)
    job_ids = []
    for job in jobs:
        job.status = "running"
        job.started_at = now
        job_ids.append(job.id)

    session.commit()
    return job_ids


def release_job_to_pending(session: Session, job_id: int) -> None:
    job = session.get(CollectJob, job_id)
    if job and job.status == "running":
        job.status = "pending"
        job.started_at = None
        session.commit()


def _execute_claimed_job(session: Session, client: BaostockClient, job_id: int) -> None:
    job = session.get(CollectJob, job_id)
    if not job or job.status != "running":
        return

    try:
        if job.job_type == "catchup_daily_update":
            run_catchup_job(session, client, job_id)
        elif job.job_type in {
            "sync_stock_meta",
            "sync_industry",
            "sync_industry_boards",
            "sync_trade_calendar",
            "daily_update",
            "update_weekly",
            "update_monthly",
            "retry_failed_jobs",
            "quality_check",
        }:
            _execute_queued_job(session, client, job)
        else:
            items = session.scalars(
                select(CollectJobItem).where(CollectJobItem.job_id == job_id)
            ).all()
            for item in items:
                src_item_id = (item.params or {}).get("retry_of_item_id")
                src_item = session.get(CollectJobItem, src_item_id) if src_item_id else None
                max_attempts = max_attempts_for_item(item)

                if src_item:
                    src_item.attempt_count += 1
                    session.flush()

                collect_kline_item(session, client, item)

                if src_item:
                    item = session.get(CollectJobItem, item.id)
                    src_item = session.get(CollectJobItem, src_item.id)
                    if item and src_item:
                        apply_retry_outcome(session, item, src_item, max_attempts)
                        session.commit()

            finalize_job(session, job)
            session.commit()
    except Exception as e:
        job = session.get(CollectJob, job_id)
        if job:
            job.status = "failed"
            job.error_message = str(e)
            job.finished_at = datetime.now(timezone.utc)
            session.commit()
        logger.exception("Failed to run pending job %s", job_id)
        raise


def _execute_queued_job(session: Session, client: BaostockClient, job: CollectJob) -> None:
    params = job.params or {}

    if job.job_type == "sync_stock_meta":
        sync_stock_meta(session, client, _date_param(params, "snapshot_date"), job=job)
    elif job.job_type == "sync_industry":
        sync_industry(session, client, _date_param(params, "snapshot_date"), job=job)
    elif job.job_type == "sync_industry_boards":
        sync_industry_boards(
            session,
            _date_param(params, "snapshot_date"),
            sleep_seconds=float(params.get("sleep_seconds", 0.35)),
            source=str(params.get("source", "auto")),
            job=job,
        )
    elif job.job_type == "sync_trade_calendar":
        sync_trade_calendar(session, client, _date_param(params, "start"), _date_param(params, "end"), job=job)
    elif job.job_type == "daily_update":
        trade_date = _date_param(params, "trade_date")
        ensure_trade_calendar_for_date(session, client, trade_date)
        daily_update_klines(session, client, trade_date, job=job)
    elif job.job_type == "update_weekly":
        update_weekly_monthly(session, client, "week", _date_param(params, "end_date"), job=job)
    elif job.job_type == "update_monthly":
        update_weekly_monthly(session, client, "month", _date_param(params, "end_date"), job=job)
    elif job.job_type == "retry_failed_jobs":
        retry_failed_items(
            session,
            client,
            int(params.get("max_attempts", settings.failed_job_max_attempts)),
            int(params.get("limit", settings.failed_job_retry_limit)),
            job=job,
        )
    elif job.job_type == "quality_check":
        issues = run_quality_check(session, int(params["target_job_id"]))
        finalize_job(session, job, inserted_rows=issues, updated_rows=0)
        session.commit()


def _date_param(params: dict, key: str):
    from datetime import date

    value = params.get(key)
    if isinstance(value, date):
        return value
    if not value:
        raise ValueError(f"Missing queued job date param: {key}")
    return date.fromisoformat(str(value))


def run_pending_jobs(session: Session, client: BaostockClient, limit: int) -> int:
    job_ids = claim_pending_jobs(session, limit)
    if not job_ids:
        return 0

    executed = 0
    for job_id in job_ids:
        with acquire_collect_lock(session) as acquired:
            if not acquired:
                logger.warning(
                    "Could not acquire lock for job %s; %s",
                    job_id,
                    format_lock_contention_message(session),
                )
                release_job_to_pending(session, job_id)
                continue
            try:
                logger.info("Executing pending job %s", job_id)
                _execute_claimed_job(session, client, job_id)
                executed += 1
            except Exception:
                continue

    return executed


def run_loop(sleep_seconds: int = 10, limit: int | None = None):
    limit = limit or settings.pending_job_runner_limit
    logger.info("Starting pending job runner loop (sleep=%ds, limit=%d)", sleep_seconds, limit)
    while True:
        session = SessionLocal()
        client = BaostockClient()
        try:
            count = run_pending_jobs(session, client, limit)
            if count:
                logger.info("Executed %d pending jobs", count)
        except Exception:
            logger.exception("Error in pending job runner")
        finally:
            client.logout()
            session.close()
        time.sleep(sleep_seconds)
