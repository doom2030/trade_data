import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CollectJob, CollectJobItem
from collector.baostock_client import BaostockClient
from collector.job_helper import create_job, create_job_item, finalize_job
from collector.kline_sync import collect_kline_item
from collector.quality_check import resolve_quality_checks

logger = logging.getLogger(__name__)
settings = get_settings()

RETRYABLE_STATUSES = frozenset({"failed", "exhausted"})


def is_retry_child_item(item: CollectJobItem) -> bool:
    return bool((item.params or {}).get("retry_of_item_id"))


def is_stale_running_item(item: CollectJobItem, stale_minutes: int) -> bool:
    if item.status != "running" or not item.started_at:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
    return item.started_at < cutoff


def can_manual_retry_item(item: CollectJobItem, stale_minutes: int | None = None) -> bool:
    stale_minutes = stale_minutes or settings.pending_job_stale_minutes
    if item.status in RETRYABLE_STATUSES:
        return True
    return is_stale_running_item(item, stale_minutes)


def max_attempts_for_item(item: CollectJobItem | None) -> int:
    if item and item.params and "max_attempts" in item.params:
        return int(item.params["max_attempts"])
    return settings.failed_job_max_attempts


def apply_retry_outcome(
    session: Session,
    new_item: CollectJobItem,
    src_item: CollectJobItem,
    max_attempts: int,
) -> None:
    if new_item.status == "success":
        src_item.status = "compensated"
        if src_item.symbol and src_item.frequency:
            resolve_quality_checks(
                session,
                src_item.symbol,
                src_item.frequency,
                src_item.adjust_flag,
                src_item.start_date,
                src_item.end_date,
            )
    elif src_item.attempt_count >= max_attempts:
        src_item.status = "exhausted"


def is_original_failed_item_clause():
    return or_(
        CollectJobItem.params.is_(None),
        CollectJobItem.params["retry_of_item_id"].astext.is_(None),
    )


def retry_failed_items(session: Session, client: BaostockClient, max_attempts: int, limit: int) -> int:
    failed_items = session.scalars(
        select(CollectJobItem)
        .where(
            CollectJobItem.status == "failed",
            CollectJobItem.attempt_count < max_attempts,
            is_original_failed_item_clause(),
        )
        .order_by(CollectJobItem.created_at)
        .limit(limit)
    ).all()

    if not failed_items:
        return 0

    job = create_job(session, "retry_failed_jobs")
    session.commit()

    retried = 0
    for src_item in failed_items:
        src_item.attempt_count += 1
        new_item = create_job_item(
            session,
            job.id,
            symbol=src_item.symbol,
            frequency=src_item.frequency,
            adjust_flag=src_item.adjust_flag,
            start_date=src_item.start_date,
            end_date=src_item.end_date,
            params={"retry_of_item_id": src_item.id},
        )
        session.commit()

        collect_kline_item(session, client, new_item)

        src_item = session.get(CollectJobItem, src_item.id)
        new_item = session.get(CollectJobItem, new_item.id)
        if src_item and new_item:
            apply_retry_outcome(session, new_item, src_item, max_attempts)

        session.commit()
        retried += 1

    finalize_job(session, job)
    session.commit()
    return retried


def retry_failed_job(
    session: Session,
    job_id: int,
    only_failed: bool = True,
    max_attempts: int = 3,
) -> CollectJob:
    src_job = session.get(CollectJob, job_id)
    if not src_job:
        raise ValueError(f"Job {job_id} not found")

    query = select(CollectJobItem).where(CollectJobItem.job_id == job_id)
    if only_failed:
        query = query.where(CollectJobItem.status.in_(["failed", "exhausted"]))
    items = session.scalars(query).all()
    retryable = [item for item in items if not is_retry_child_item(item)]
    if not retryable:
        raise ValueError("No retryable items found for this job")

    job = create_job(
        session,
        "manual_retry_failed_job",
        retry_of_job_id=job_id,
        status="pending",
    )

    for src_item in retryable:
        create_job_item(
            session,
            job.id,
            symbol=src_item.symbol,
            frequency=src_item.frequency,
            adjust_flag=src_item.adjust_flag,
            start_date=src_item.start_date,
            end_date=src_item.end_date,
            params={"retry_of_item_id": src_item.id, "max_attempts": max_attempts},
        )

    session.commit()
    return job


def retry_failed_item(
    session: Session,
    item_id: int,
    max_attempts: int = 3,
) -> CollectJob:
    src_item = session.get(CollectJobItem, item_id)
    if not src_item:
        raise ValueError(f"Item {item_id} not found")

    if not can_manual_retry_item(src_item):
        raise ValueError(
            f"Item {item_id} status={src_item.status} is not retryable; "
            "only failed, exhausted, or stale running items can be retried"
        )

    if is_retry_child_item(src_item):
        raise ValueError(f"Item {item_id} is a retry child item; retry the original failed item instead")

    existing = session.scalars(
        select(CollectJob).where(
            CollectJob.retry_of_item_id == item_id,
            CollectJob.status.in_(["pending", "running"]),
        )
    ).first()
    if existing:
        return existing

    job = create_job(
        session,
        "manual_retry_failed_item",
        retry_of_item_id=item_id,
        status="pending",
    )
    create_job_item(
        session,
        job.id,
        symbol=src_item.symbol,
        frequency=src_item.frequency,
        adjust_flag=src_item.adjust_flag,
        start_date=src_item.start_date,
        end_date=src_item.end_date,
        params={"retry_of_item_id": item_id, "max_attempts": max_attempts},
    )
    session.commit()
    return job
