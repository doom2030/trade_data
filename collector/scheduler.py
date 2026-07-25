"""In-process schedule helpers and run loop for daily/industry jobs."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import CollectJob
from collector.baostock_client import BaostockClient
from collector.collect_lock import acquire_collect_lock, format_lock_contention_message
from collector.daily_update_runner import run_daily_update
from collector.industry_board_sync import sync_industry_boards

logger = logging.getLogger(__name__)
settings = get_settings()

_ACTIVE_STATUSES = ("pending", "running", "success", "partial_success")


def parse_weekdays(value: str) -> set[int]:
    """Parse comma-separated weekdays. 0=Monday … 6=Sunday (datetime.weekday)."""
    days: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        day = int(part)
        if day < 0 or day > 6:
            raise ValueError(f"Invalid weekday {day}; expected 0-6")
        days.add(day)
    return days


def is_schedule_due(
    now: datetime,
    *,
    hour: int,
    minute: int,
    weekdays: set[int],
    already_ran_on: date | None,
) -> bool:
    """Return True when local now is at/after schedule time and not yet run today."""
    if now.weekday() not in weekdays:
        return False
    if (now.hour, now.minute) < (hour, minute):
        return False
    if already_ran_on == now.date():
        return False
    return True


def has_active_daily_update(session: Session, trade_date: date) -> bool:
    job_id = session.scalar(
        select(CollectJob.id)
        .where(
            CollectJob.job_type == "daily_update",
            CollectJob.target_trade_date == trade_date,
            CollectJob.status.in_(_ACTIVE_STATUSES),
        )
        .limit(1)
    )
    return job_id is not None


def has_active_industry_sync_on(session: Session, day: date, tz: ZoneInfo) -> bool:
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    end = start + timedelta(days=1)
    job_id = session.scalar(
        select(CollectJob.id)
        .where(
            CollectJob.job_type == "sync_industry_boards",
            CollectJob.status.in_(_ACTIVE_STATUSES),
            CollectJob.created_at >= start,
            CollectJob.created_at < end,
        )
        .limit(1)
    )
    return job_id is not None


def run_industry_board_sync(snapshot_date: date | None = None) -> bool:
    target = snapshot_date or date.today()
    session = SessionLocal()
    client = BaostockClient()
    try:
        with acquire_collect_lock(session) as acquired:
            if not acquired:
                logger.warning(
                    "industry sync skipped: %s",
                    format_lock_contention_message(session),
                )
                return False
            boards, members, source = sync_industry_boards(
                session,
                target,
                source="auto",
            )
            logger.info(
                "Industry board sync done source=%s boards=%s members=%s",
                source,
                boards,
                members,
            )
            return True
    finally:
        client.logout()
        session.close()


def run_scheduler_loop() -> None:
    tz = ZoneInfo(settings.scheduler_timezone)
    daily_weekdays = parse_weekdays(settings.scheduler_daily_update_weekdays)
    industry_weekdays = parse_weekdays(settings.scheduler_industry_sync_weekdays)
    poll = max(5, int(settings.scheduler_poll_seconds))

    logger.info(
        "Scheduler started tz=%s daily=%02d:%02d weekdays=%s industry=%s@%02d:%02d weekdays=%s poll=%ss",
        settings.scheduler_timezone,
        settings.scheduler_daily_update_hour,
        settings.scheduler_daily_update_minute,
        sorted(daily_weekdays),
        "on" if settings.scheduler_industry_sync_enabled else "off",
        settings.scheduler_industry_sync_hour,
        settings.scheduler_industry_sync_minute,
        sorted(industry_weekdays),
        poll,
    )

    last_daily_attempt: date | None = None
    last_industry_attempt: date | None = None

    while True:
        now = datetime.now(tz)
        today = now.date()

        if settings.scheduler_daily_update_enabled and is_schedule_due(
            now,
            hour=settings.scheduler_daily_update_hour,
            minute=settings.scheduler_daily_update_minute,
            weekdays=daily_weekdays,
            already_ran_on=last_daily_attempt,
        ):
            session = SessionLocal()
            try:
                exists = has_active_daily_update(session, today)
            finally:
                session.close()

            if exists:
                logger.info("Skip daily_update: active job already exists for %s", today)
                last_daily_attempt = today
            else:
                logger.info("Triggering scheduled daily_update for %s", today)
                result = run_daily_update(today)
                if result.ok or not result.skipped_lock:
                    # Mark attempted unless only lock contention (retry next poll).
                    last_daily_attempt = today
                if result.skipped_lock:
                    logger.warning("daily_update lock busy; will retry")
                elif result.ok:
                    logger.info("Scheduled daily_update finished: %s", result.message)
                else:
                    logger.error("Scheduled daily_update failed: %s", result.message)

        if (
            settings.scheduler_industry_sync_enabled
            and is_schedule_due(
                now,
                hour=settings.scheduler_industry_sync_hour,
                minute=settings.scheduler_industry_sync_minute,
                weekdays=industry_weekdays,
                already_ran_on=last_industry_attempt,
            )
        ):
            session = SessionLocal()
            try:
                exists = has_active_industry_sync_on(session, today, tz)
            finally:
                session.close()

            if exists:
                logger.info("Skip industry sync: active job already exists around %s", today)
                last_industry_attempt = today
            else:
                logger.info("Triggering scheduled industry board sync for %s", today)
                ok = run_industry_board_sync(today)
                if ok:
                    last_industry_attempt = today
                else:
                    logger.warning("industry sync lock busy or failed; will retry")

        time.sleep(poll)
