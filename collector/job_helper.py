from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CollectJob, CollectJobItem, CollectJobLog


def create_job(
    session: Session,
    job_type: str,
    *,
    frequency: str | None = None,
    adjust_flag: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    target_trade_date: date | None = None,
    retry_of_job_id: int | None = None,
    retry_of_item_id: int | None = None,
    params: dict | None = None,
    status: str = "running",
) -> CollectJob:
    job = CollectJob(
        job_type=job_type,
        status=status,
        frequency=frequency,
        adjust_flag=adjust_flag,
        start_date=start_date,
        end_date=end_date,
        target_trade_date=target_trade_date,
        retry_of_job_id=retry_of_job_id,
        retry_of_item_id=retry_of_item_id,
        params=params,
        started_at=datetime.now(timezone.utc) if status == "running" else None,
    )
    session.add(job)
    session.flush()
    return job


def set_job_progress(session: Session, job: CollectJob, stage: str, **extra) -> None:
    progress = {
        "stage": stage,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    job.params = {**(job.params or {}), "progress": progress}
    session.flush()


def append_job_log(
    session: Session,
    job: CollectJob,
    message: str,
    *,
    level: str = "info",
    payload: dict | None = None,
) -> None:
    session.add(
        CollectJobLog(
            job_id=job.id,
            level=level,
            message=message,
            payload=payload,
        )
    )
    session.flush()


def create_job_item(
    session: Session,
    job_id: int,
    *,
    symbol: str | None = None,
    frequency: str | None = None,
    adjust_flag: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    status: str = "pending",
    params: dict | None = None,
) -> CollectJobItem:
    item = CollectJobItem(
        job_id=job_id,
        symbol=symbol,
        frequency=frequency,
        adjust_flag=adjust_flag,
        start_date=start_date,
        end_date=end_date,
        status=status,
        params=params,
    )
    session.add(item)
    session.flush()
    return item


def finalize_job(
    session: Session,
    job: CollectJob,
    *,
    inserted_rows: int | None = None,
    updated_rows: int | None = None,
) -> None:
    """Finalize job counters and status.

    Itemized jobs (e.g. kline backfill): aggregate from CollectJobItem rows.
    Bulk jobs with no items (e.g. sync_industry): treat as a single successful
    unit and accept optional row counts so totals are not left at zero.
    """
    items = session.scalars(select(CollectJobItem).where(CollectJobItem.job_id == job.id)).all()

    if not items:
        job.total_items = 1
        job.success_items = 1
        job.failed_items = 0
        job.skipped_items = 0
        job.exhausted_items = 0
        job.compensated_items = 0
        if inserted_rows is not None:
            job.inserted_rows = inserted_rows
        if updated_rows is not None:
            job.updated_rows = updated_rows
        job.status = "success"
        job.finished_at = datetime.now(timezone.utc)
        session.flush()
        return

    job.total_items = len(items)
    job.success_items = sum(1 for i in items if i.status == "success")
    job.failed_items = sum(1 for i in items if i.status == "failed")
    job.skipped_items = sum(1 for i in items if i.status == "skipped")
    job.exhausted_items = sum(1 for i in items if i.status == "exhausted")
    job.compensated_items = sum(1 for i in items if i.status == "compensated")
    job.inserted_rows = sum(i.inserted_rows for i in items) if inserted_rows is None else inserted_rows
    job.updated_rows = sum(i.updated_rows for i in items) if updated_rows is None else updated_rows

    effective = job.total_items - job.skipped_items
    if effective == 0:
        job.status = "success"
        if job.params is None:
            job.params = {}
        job.params["all_skipped"] = True
    else:
        fail_rate = job.failed_items / effective
        if fail_rate == 0:
            job.status = "success"
        elif fail_rate <= 0.05:
            job.status = "partial_success"
        else:
            job.status = "failed"

    job.finished_at = datetime.now(timezone.utc)
    session.flush()


def mark_stale_running_jobs(session: Session, stale_minutes: int) -> int:
    cutoff = datetime.now(timezone.utc) - __import__("datetime").timedelta(minutes=stale_minutes)
    stale_jobs = session.scalars(
        select(CollectJob).where(
            CollectJob.status == "running",
            CollectJob.started_at < cutoff,
        )
    ).all()
    count = 0
    for job in stale_jobs:
        job.status = "failed"
        job.error_message = f"Stale running job exceeded {stale_minutes} minutes"
        job.finished_at = datetime.now(timezone.utc)
        items = session.scalars(
            select(CollectJobItem).where(
                CollectJobItem.job_id == job.id,
                CollectJobItem.status == "running",
            )
        ).all()
        for item in items:
            item.status = "failed"
            item.error_message = "Stale running item"
            item.finished_at = datetime.now(timezone.utc)
        count += 1
    session.flush()
    return count
