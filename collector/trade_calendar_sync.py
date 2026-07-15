import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CollectJob, TradeCalendar
from collector.baostock_client import BaostockClient, BaostockError
from collector.job_helper import append_job_log, create_job, finalize_job

logger = logging.getLogger(__name__)
settings = get_settings()


def ensure_trade_calendar_for_date(
    session: Session,
    client: BaostockClient,
    trade_date: date,
    window_days: int = 14,
) -> bool:
    if session.get(TradeCalendar, trade_date) is not None:
        return True

    start_date = trade_date - timedelta(days=window_days)
    end_date = trade_date + timedelta(days=window_days)
    logger.info(
        "Trade calendar missing for %s, syncing %s..%s",
        trade_date,
        start_date,
        end_date,
    )
    sync_trade_calendar(session, client, start_date, end_date)
    return session.get(TradeCalendar, trade_date) is not None


def sync_trade_calendar(
    session: Session,
    client: BaostockClient,
    start_date: date,
    end_date: date,
    job: CollectJob | None = None,
) -> int:
    job = job or create_job(
        session,
        "sync_trade_calendar",
        start_date=start_date,
        end_date=end_date,
    )
    session.commit()

    try:
        try:
            append_job_log(
                session,
                job,
                "开始请求 baostock 交易日历",
                payload={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            )
            session.commit()
            rows = client.query_trade_calendar(start_date, end_date)
            source = "baostock"
            upserted = _upsert_calendar_rows(session, rows, source)
        except BaostockError:
            append_job_log(session, job, "baostock 交易日历不可用，开始用基准股票推断", level="error")
            logger.info("baostock trade calendar unavailable, inferring from benchmark symbols")
            upserted = _infer_calendar(session, client, start_date, end_date)

        finalize_job(session, job, inserted_rows=upserted)
        append_job_log(session, job, "交易日历写入完成", payload={"rows": upserted})
        session.commit()
        return upserted
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.finished_at = datetime.now(timezone.utc)
        session.commit()
        raise


def _upsert_calendar_rows(session: Session, rows: list[dict], source: str) -> int:
    count = 0
    for row in rows:
        stmt = insert(__import__("app.models", fromlist=["TradeCalendar"]).TradeCalendar).values(
            trade_date=row["trade_date"],
            is_trading_day=row["is_trading_day"],
            source=source,
            raw_payload=row.get("raw_payload"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["trade_date"],
            set_={
                "is_trading_day": row["is_trading_day"],
                "source": source,
                "raw_payload": row.get("raw_payload"),
                "updated_at": datetime.now(timezone.utc),
            },
        )
        session.execute(stmt)
        count += 1
    return count


def _infer_calendar(session: Session, client: BaostockClient, start_date: date, end_date: date) -> int:
    from app.models import TradeCalendar

    benchmarks = settings.benchmark_symbols
    threshold = settings.trade_calendar_min_valid_klines
    count = 0
    current = start_date
    while current <= end_date:
        sample_results = {}
        valid_count = 0
        for sym in benchmarks:
            try:
                klines = client.query_kline(sym, "day", current, current, "none")
                has_data = len(klines) > 0
                sample_results[sym] = {"has_data": has_data, "count": len(klines)}
                if has_data:
                    valid_count += 1
            except BaostockError as e:
                sample_results[sym] = {"error": e.code, "message": e.message}

        is_trading = valid_count >= threshold
        raw_payload = {
            "benchmark_symbols": benchmarks,
            "threshold": threshold,
            "valid_count": valid_count,
            "sample_results": sample_results,
            "source_method": "infer",
        }
        stmt = insert(TradeCalendar).values(
            trade_date=current,
            is_trading_day=is_trading,
            source="baostock_infer",
            raw_payload=raw_payload,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["trade_date"],
            set_={
                "is_trading_day": is_trading,
                "source": "baostock_infer",
                "raw_payload": raw_payload,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        session.execute(stmt)
        count += 1
        current += timedelta(days=1)
    return count
