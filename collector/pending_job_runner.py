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
from collector.job_helper import finalize_job, mark_stale_running_jobs
from collector.kline_sync import collect_kline_item, run_catchup_job
from collector.retry_service import apply_retry_outcome, max_attempts_for_item

logger = logging.getLogger(__name__)
settings = get_settings()

PENDING_JOB_TYPES = {
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
