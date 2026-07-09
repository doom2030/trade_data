import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CollectJob, CollectJobItem, StockMaster, StockSuspension, TradeCalendar
from collector.baostock_client import BaostockClient, BaostockError
from collector.job_helper import create_job, create_job_item, finalize_job
from collector.kline_table_router import get_kline_model, make_period_start

logger = logging.getLogger(__name__)
settings = get_settings()

# Week/month bars are sparse; treat calendar gaps larger than this as missing periods.
_WEEK_GAP_DAYS = 14
_MONTH_GAP_DAYS = 45


def is_trading_day(session: Session, trade_date: date) -> bool:
    cal = session.get(TradeCalendar, trade_date)
    if cal is None:
        logger.warning("No trade calendar entry for %s, treating as non-trading day", trade_date)
        return False
    return cal.is_trading_day


def effective_start(stock: StockMaster, default_start: date) -> date:
    if stock.ipo_date and stock.ipo_date > default_start:
        return stock.ipo_date
    return default_start


def collapse_sorted_dates_to_ranges(dates: list[date]) -> list[tuple[date, date]]:
    """Collapse a sorted list of dates into inclusive contiguous calendar ranges."""
    if not dates:
        return []
    ranges: list[tuple[date, date]] = []
    range_start = prev = dates[0]
    for current in dates[1:]:
        if current == prev + timedelta(days=1):
            prev = current
            continue
        ranges.append((range_start, prev))
        range_start = prev = current
    ranges.append((range_start, prev))
    return ranges


def collapse_trading_day_gaps(
    trading_days: list[date],
    missing: list[date],
) -> list[tuple[date, date]]:
    """Collapse missing trading days into ranges using adjacency on the trading calendar."""
    if not missing:
        return []
    index = {d: i for i, d in enumerate(trading_days)}
    ranges: list[tuple[date, date]] = []
    range_start = prev = missing[0]
    for current in missing[1:]:
        if index[current] == index[prev] + 1:
            prev = current
            continue
        ranges.append((range_start, prev))
        range_start = prev = current
    ranges.append((range_start, prev))
    return ranges


def missing_kline_ranges(
    session: Session,
    *,
    symbol: str,
    frequency: str,
    adjust_flag: str,
    start: date,
    end: date,
) -> list[tuple[date, date]]:
    """Return inclusive date ranges that still need fetching from baostock.

    Day bars: compare against trading calendar (open suspensions count as covered).
    Week/month: cover leading/trailing holes and large gaps between existing bars.
    """
    if start > end:
        return []

    model = get_kline_model(frequency)
    existing = session.scalars(
        select(model.trade_date)
        .where(
            model.symbol == symbol,
            model.adjust_flag == adjust_flag,
            model.trade_date >= start,
            model.trade_date <= end,
        )
        .order_by(model.trade_date)
    ).all()

    if frequency == "day":
        trading_days = session.scalars(
            select(TradeCalendar.trade_date)
            .where(
                TradeCalendar.is_trading_day.is_(True),
                TradeCalendar.trade_date >= start,
                TradeCalendar.trade_date <= end,
            )
            .order_by(TradeCalendar.trade_date)
        ).all()
        if not trading_days:
            # Without a trading calendar we cannot detect day gaps safely.
            return [(start, end)]

        existing_set = set(existing)
        suspended = set(
            session.scalars(
                select(StockSuspension.trade_date).where(
                    StockSuspension.symbol == symbol,
                    StockSuspension.trade_date >= start,
                    StockSuspension.trade_date <= end,
                    StockSuspension.resolved_at.is_(None),
                )
            ).all()
        )
        missing = [d for d in trading_days if d not in existing_set and d not in suspended]
        return collapse_trading_day_gaps(trading_days, missing)

    # week / month: no dense calendar — fill leading, trailing, and large interior gaps.
    if not existing:
        return [(start, end)]

    gap_limit = _WEEK_GAP_DAYS if frequency == "week" else _MONTH_GAP_DAYS
    missing_dates: list[date] = []
    if existing[0] > start:
        cursor = start
        while cursor < existing[0]:
            missing_dates.append(cursor)
            cursor += timedelta(days=1)
    for left, right in zip(existing, existing[1:]):
        if (right - left).days > gap_limit:
            cursor = left + timedelta(days=1)
            while cursor < right:
                missing_dates.append(cursor)
                cursor += timedelta(days=1)
    if existing[-1] < end:
        cursor = existing[-1] + timedelta(days=1)
        while cursor <= end:
            missing_dates.append(cursor)
            cursor += timedelta(days=1)
    return collapse_sorted_dates_to_ranges(missing_dates)


def upsert_klines(session: Session, frequency: str, rows: list[dict]) -> tuple[int, int]:
    if not rows:
        return 0, 0
    model = get_kline_model(frequency)
    inserted = 0
    updated = 0
    batch_size = settings.collect_batch_size

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        for row in batch:
            if row.get("is_st"):
                continue
            trade_date = row["trade_date"]
            values = {
                "symbol": row["symbol"],
                "trade_date": trade_date,
                "adjust_flag": row["adjust_flag"],
                "period_start": make_period_start(trade_date),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "preclose": row.get("preclose"),
                "volume": row.get("volume"),
                "amount": row.get("amount"),
                "turn": row.get("turn"),
                "pct_chg": row.get("pct_chg"),
                "tradestatus": row.get("tradestatus"),
                "is_st": row.get("is_st"),
                "source": "baostock",
                "raw_payload": row.get("raw_payload"),
                "updated_at": datetime.now(timezone.utc),
            }
            existing = session.get(
                model, {"symbol": row["symbol"], "trade_date": trade_date, "adjust_flag": row["adjust_flag"]}
            )
            stmt = insert(model).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol", "trade_date", "adjust_flag"],
                set_={k: v for k, v in values.items() if k not in ("symbol", "trade_date", "adjust_flag")},
            )
            session.execute(stmt)
            if existing:
                updated += 1
            else:
                inserted += 1
    return inserted, updated


def collect_kline_item(
    session: Session,
    client: BaostockClient,
    item: CollectJobItem,
) -> None:
    item.status = "running"
    item.started_at = datetime.now(timezone.utc)
    session.flush()

    if not item.symbol or not item.frequency or not item.adjust_flag:
        item.status = "failed"
        item.error_message = "Missing symbol/frequency/adjust_flag"
        item.finished_at = datetime.now(timezone.utc)
        return

    stock = session.get(StockMaster, item.symbol)
    if not stock:
        item.status = "failed"
        item.error_message = "Stock not found"
        item.finished_at = datetime.now(timezone.utc)
        return

    start = item.start_date
    end = item.end_date
    if not start or not end:
        item.status = "failed"
        item.error_message = "Missing date range"
        item.finished_at = datetime.now(timezone.utc)
        return

    if stock.ipo_date and end < stock.ipo_date:
        item.status = "skipped"
        item.error_message = "Before IPO date"
        item.finished_at = datetime.now(timezone.utc)
        return

    if stock.ipo_date and start < stock.ipo_date:
        start = stock.ipo_date

    if stock.status != "active":
        item.status = "skipped"
        item.error_message = f"Stock status is {stock.status}"
        item.finished_at = datetime.now(timezone.utc)
        return

    try:
        rows = client.query_kline(item.symbol, item.frequency, start, end, item.adjust_flag)
        st_rows = sum(1 for row in rows if row.get("is_st"))
        ins, upd = upsert_klines(session, item.frequency, rows)
        item.inserted_rows = ins
        item.updated_rows = upd
        if rows and ins + upd == 0 and st_rows == len(rows):
            params = dict(item.params or {})
            params["st_filtered_all"] = True
            item.params = params
        item.status = "success"
        item.finished_at = datetime.now(timezone.utc)
        session.commit()
    except BaostockError as e:
        session.rollback()
        failed = session.get(CollectJobItem, item.id)
        if failed:
            failed.status = "failed"
            failed.error_code = e.code
            failed.error_message = e.message
            failed.finished_at = datetime.now(timezone.utc)
            session.commit()
    except Exception as e:
        session.rollback()
        failed = session.get(CollectJobItem, item.id)
        if failed:
            failed.status = "failed"
            failed.error_message = str(e)
            failed.finished_at = datetime.now(timezone.utc)
            session.commit()


def _execute_daily_date_for_job(
    session: Session,
    client: BaostockClient,
    job_id: int,
    trade_date: date,
) -> list[CollectJobItem]:
    stocks = session.scalars(select(StockMaster).where(StockMaster.status == "active")).all()
    adjust_flags = settings.adjust_flags

    for stock in stocks:
        if stock.ipo_date and trade_date < stock.ipo_date:
            for adj in adjust_flags:
                item = create_job_item(
                    session,
                    job_id,
                    symbol=stock.symbol,
                    frequency="day",
                    adjust_flag=adj,
                    start_date=trade_date,
                    end_date=trade_date,
                )
                item.status = "skipped"
                item.error_message = "Before IPO"
                item.finished_at = datetime.now(timezone.utc)
            continue
        for adj in adjust_flags:
            create_job_item(
                session,
                job_id,
                symbol=stock.symbol,
                frequency="day",
                adjust_flag=adj,
                start_date=trade_date,
                end_date=trade_date,
            )

    session.commit()

    day_items = session.scalars(
        select(CollectJobItem).where(
            CollectJobItem.job_id == job_id,
            CollectJobItem.frequency == "day",
            CollectJobItem.start_date == trade_date,
            CollectJobItem.end_date == trade_date,
        )
    ).all()

    for item in day_items:
        if item.status == "pending":
            collect_kline_item(session, client, item)

    _process_suspensions_from_items(session, trade_date, job_id, day_items)
    session.commit()
    return day_items


def backfill_klines(
    session: Session,
    client: BaostockClient,
    frequency: str,
    adjust_flags: list[str],
    start_date: date | None = None,
    end_date: date | None = None,
    symbols: list[str] | None = None,
    *,
    skip_existing: bool = True,
) -> CollectJob:
    """Backfill klines. When skip_existing=True (default), only request missing ranges."""
    default_start = date.fromisoformat(settings.default_history_start_date)
    start = start_date or default_start
    end = end_date or date.today()

    job = create_job(
        session,
        "backfill_kline",
        frequency=frequency,
        start_date=start,
        end_date=end,
        params={"skip_existing": skip_existing},
    )

    if symbols:
        stocks = session.scalars(
            select(StockMaster).where(StockMaster.symbol.in_(symbols), StockMaster.status == "active")
        ).all()
    else:
        stocks = session.scalars(select(StockMaster).where(StockMaster.status == "active")).all()

    now = datetime.now(timezone.utc)
    for stock in stocks:
        eff_start = effective_start(stock, start)
        if eff_start > end:
            continue
        for adj in adjust_flags:
            if skip_existing:
                ranges = missing_kline_ranges(
                    session,
                    symbol=stock.symbol,
                    frequency=frequency,
                    adjust_flag=adj,
                    start=eff_start,
                    end=end,
                )
            else:
                ranges = [(eff_start, end)]

            if not ranges:
                item = create_job_item(
                    session,
                    job.id,
                    symbol=stock.symbol,
                    frequency=frequency,
                    adjust_flag=adj,
                    start_date=eff_start,
                    end_date=end,
                )
                item.status = "skipped"
                item.error_message = "Already complete in range"
                item.finished_at = now
                continue

            for range_start, range_end in ranges:
                create_job_item(
                    session,
                    job.id,
                    symbol=stock.symbol,
                    frequency=frequency,
                    adjust_flag=adj,
                    start_date=range_start,
                    end_date=range_end,
                )

    session.commit()

    items = session.scalars(select(CollectJobItem).where(CollectJobItem.job_id == job.id)).all()
    for item in items:
        if item.status == "pending":
            collect_kline_item(session, client, item)

    finalize_job(session, job)
    session.commit()
    return job


def daily_update_klines(
    session: Session,
    client: BaostockClient,
    trade_date: date,
    job_type: str = "daily_update",
) -> CollectJob:
    if not is_trading_day(session, trade_date):
        job = create_job(
            session,
            job_type,
            frequency="day",
            target_trade_date=trade_date,
            params={"skip_reason": "non_trading_day"},
        )
        session.commit()
        finalize_job(session, job)
        session.commit()
        return job

    job = create_job(
        session,
        job_type,
        frequency="day",
        target_trade_date=trade_date,
    )
    session.commit()

    _execute_daily_date_for_job(session, client, job.id, trade_date)
    finalize_job(session, job)
    session.commit()
    return job


def update_weekly_monthly(
    session: Session,
    client: BaostockClient,
    frequency: str,
    end_date: date,
    periods: int = 2,
) -> CollectJob:
    job_type = "update_weekly" if frequency == "week" else "update_monthly"
    job = create_job(
        session,
        job_type,
        frequency=frequency,
        end_date=end_date,
    )

    if frequency == "week":
        start_date = end_date - timedelta(weeks=periods * 2)
    else:
        start_date = end_date - timedelta(days=periods * 62)

    stocks = session.scalars(select(StockMaster).where(StockMaster.status == "active")).all()
    for stock in stocks:
        eff_start = effective_start(stock, start_date)
        for adj in settings.adjust_flags:
            create_job_item(
                session,
                job.id,
                symbol=stock.symbol,
                frequency=frequency,
                adjust_flag=adj,
                start_date=eff_start,
                end_date=end_date,
            )

    session.commit()
    items = session.scalars(select(CollectJobItem).where(CollectJobItem.job_id == job.id)).all()
    for item in items:
        collect_kline_item(session, client, item)

    finalize_job(session, job)
    session.commit()
    return job


def analyze_suspension_from_items(
    items_by_adjust: dict[str, CollectJobItem],
    adjust_flags: list[str],
) -> tuple[str | None, dict[str, int], dict[str, str]]:
    """Return (outcome, kline_counts, errors).

    outcome: None = cannot infer, 'suspended' = all adjusts empty, 'has_data' = at least one row.
    """
    kline_counts: dict[str, int] = {}
    errors: dict[str, str] = {}

    for adj in adjust_flags:
        item = items_by_adjust.get(adj)
        if item is None:
            return None, kline_counts, errors
        if item.status == "skipped":
            return None, kline_counts, errors
        if item.status == "failed":
            errors[adj] = item.error_message or item.error_code or "failed"
            continue
        if item.status != "success":
            return None, kline_counts, errors
        if (item.params or {}).get("st_filtered_all"):
            return None, kline_counts, errors
        row_count = item.inserted_rows + item.updated_rows
        kline_counts[adj] = row_count
        if row_count > 0:
            return "has_data", kline_counts, errors

    if errors:
        return None, kline_counts, errors
    if all(kline_counts.get(adj, 0) == 0 for adj in adjust_flags):
        return "suspended", kline_counts, errors
    return None, kline_counts, errors


def _process_suspensions_from_items(
    session: Session,
    trade_date: date,
    job_id: int,
    items: list[CollectJobItem],
):
    cal = session.get(TradeCalendar, trade_date)
    if cal and not cal.is_trading_day:
        return

    adjust_flags = settings.adjust_flags
    by_symbol: dict[str, dict[str, CollectJobItem]] = {}

    for item in items:
        if not item.symbol or not item.adjust_flag:
            continue
        if item.frequency != "day" or item.start_date != trade_date:
            continue
        by_symbol.setdefault(item.symbol, {})[item.adjust_flag] = item

    for symbol, adj_items in by_symbol.items():
        outcome, kline_counts, errors = analyze_suspension_from_items(adj_items, adjust_flags)
        if outcome == "has_data":
            _resolve_suspension(session, symbol, trade_date)
            continue
        if outcome != "suspended":
            continue

        existing = session.get(StockSuspension, {"symbol": symbol, "trade_date": trade_date})
        if existing and existing.resolved_at:
            continue

        raw_payload = {
            "kline_counts": kline_counts,
            "errors": errors,
            "job_id": job_id,
            "trade_date": str(trade_date),
            "source": "item_results",
        }
        stmt = insert(StockSuspension).values(
            symbol=symbol,
            trade_date=trade_date,
            reason="suspended",
            source="baostock_infer",
            raw_payload=raw_payload,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "trade_date"],
            set_={
                "raw_payload": raw_payload,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        session.execute(stmt)


def _resolve_suspension(session: Session, symbol: str, trade_date: date):
    susp = session.get(StockSuspension, {"symbol": symbol, "trade_date": trade_date})
    if susp and not susp.resolved_at:
        susp.resolved_at = datetime.now(timezone.utc)
        susp.resolved_reason = "data_arrived"


def _catchup_covered_dates(
    session: Session,
    job: CollectJob,
    range_start: date,
    range_end: date,
) -> set[date]:
    trade_dates = _catchup_trade_dates(job)
    if trade_dates:
        return {d for d in trade_dates if range_start <= d <= range_end}
    if job.start_date and job.end_date:
        days = session.scalars(
            select(TradeCalendar.trade_date).where(
                TradeCalendar.is_trading_day.is_(True),
                TradeCalendar.trade_date >= max(job.start_date, range_start),
                TradeCalendar.trade_date <= min(job.end_date, range_end),
            )
        ).all()
        return set(days)
    if job.target_trade_date and range_start <= job.target_trade_date <= range_end:
        return {job.target_trade_date}
    return set()


def _add_job_covered_dates(
    session: Session,
    jobs: list[CollectJob],
    covered: set[date],
    range_start: date,
    range_end: date,
) -> None:
    for job in jobs:
        if job.job_type == "daily_update" and job.target_trade_date:
            if range_start <= job.target_trade_date <= range_end:
                covered.add(job.target_trade_date)
        elif job.job_type == "catchup_daily_update":
            covered.update(_catchup_covered_dates(session, job, range_start, range_end))


def get_missed_trading_days(session: Session, up_to: date) -> list[date]:
    range_start = date.fromisoformat(settings.default_history_start_date)

    trading_days = session.scalars(
        select(TradeCalendar.trade_date).where(
            TradeCalendar.is_trading_day.is_(True),
            TradeCalendar.trade_date >= range_start,
            TradeCalendar.trade_date <= up_to,
        ).order_by(TradeCalendar.trade_date)
    ).all()
    trading_days = list(trading_days)
    if not trading_days:
        return []

    covered: set[date] = set()
    jobs = session.scalars(
        select(CollectJob).where(
            CollectJob.job_type.in_(["daily_update", "catchup_daily_update"]),
            CollectJob.status.in_(["success", "partial_success"]),
            or_(
                and_(
                    CollectJob.job_type == "daily_update",
                    CollectJob.target_trade_date.isnot(None),
                    CollectJob.target_trade_date >= range_start,
                    CollectJob.target_trade_date <= up_to,
                ),
                and_(
                    CollectJob.job_type == "catchup_daily_update",
                    CollectJob.start_date.isnot(None),
                    CollectJob.end_date.isnot(None),
                    CollectJob.start_date <= up_to,
                    CollectJob.end_date >= range_start,
                ),
            ),
        )
    ).all()
    _add_job_covered_dates(session, jobs, covered, range_start, up_to)

    inflight_catchup_jobs = session.scalars(
        select(CollectJob).where(
            CollectJob.job_type == "catchup_daily_update",
            CollectJob.status.in_(["pending", "running"]),
            CollectJob.start_date.isnot(None),
            CollectJob.end_date.isnot(None),
            CollectJob.start_date <= up_to,
            CollectJob.end_date >= range_start,
        )
    ).all()
    _add_job_covered_dates(session, inflight_catchup_jobs, covered, range_start, up_to)

    missed: list[date] = []
    for trade_date in trading_days:
        if trade_date not in covered:
            missed.append(trade_date)
    return missed


def create_catchup_jobs(session: Session, missed_days: list[date]) -> list[int]:
    max_days = settings.catchup_daily_max_trading_days
    job_ids = []
    for i in range(0, len(missed_days), max_days):
        batch = missed_days[i : i + max_days]
        job = create_job(
            session,
            "catchup_daily_update",
            frequency="day",
            start_date=batch[0],
            end_date=batch[-1],
            target_trade_date=batch[-1],
            status="pending",
            params={"trade_dates": [d.isoformat() for d in batch]},
        )
        job_ids.append(job.id)
    session.commit()
    return job_ids


def _catchup_trade_dates(job: CollectJob) -> list[date]:
    if job.params and job.params.get("trade_dates"):
        return [date.fromisoformat(d) for d in job.params["trade_dates"]]
    if job.start_date and job.end_date:
        return []
    return []


def run_catchup_job(session: Session, client: BaostockClient, job_id: int):
    job = session.get(CollectJob, job_id)
    if not job:
        return

    trade_dates = _catchup_trade_dates(job)
    if not trade_dates and job.start_date and job.end_date:
        trade_dates = session.scalars(
            select(TradeCalendar.trade_date).where(
                TradeCalendar.is_trading_day.is_(True),
                TradeCalendar.trade_date >= job.start_date,
                TradeCalendar.trade_date <= job.end_date,
            ).order_by(TradeCalendar.trade_date)
        ).all()
        trade_dates = list(trade_dates)

    for td in sorted(set(trade_dates)):
        if not is_trading_day(session, td):
            logger.info("Skipping non-trading day %s in catchup job %s", td, job_id)
            continue
        _execute_daily_date_for_job(session, client, job.id, td)

    finalize_job(session, job)
    session.commit()


def manual_backfill(
    session: Session,
    symbol: str,
    frequency: str,
    start: date,
    end: date,
) -> CollectJob:
    job = create_job(
        session,
        "manual_backfill_range",
        frequency=frequency,
        start_date=start,
        end_date=end,
        status="pending",
        params={"symbol": symbol},
    )
    for adj in settings.adjust_flags:
        create_job_item(
            session,
            job.id,
            symbol=symbol,
            frequency=frequency,
            adjust_flag=adj,
            start_date=start,
            end_date=end,
        )
    session.commit()
    return job
