import logging
from datetime import date, datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    CollectJob,
    CollectJobItem,
    KlineDay,
    QualityCheckResult,
    StockMaster,
    StockSuspension,
    TradeCalendar,
)
from collector.job_helper import finalize_job

logger = logging.getLogger(__name__)
settings = get_settings()


def run_quality_check(session: Session, job_id: int) -> int:
    job = session.get(CollectJob, job_id)
    if not job:
        return 0

    items = session.scalars(select(CollectJobItem).where(CollectJobItem.job_id == job_id)).all()
    issues = 0

    for item in items:
        if item.status != "success" or not item.symbol or not item.frequency:
            continue
        if item.frequency != "day":
            issues += _check_kline_ohlc(session, item, job_id)
            continue

        start = item.start_date
        end = item.end_date
        if not start or not end:
            continue

        stock = session.get(StockMaster, item.symbol)
        if not stock or stock.status != "active":
            continue

        current = start
        from datetime import timedelta

        while current <= end:
            cal = session.get(TradeCalendar, current)
            if cal and not cal.is_trading_day:
                current += timedelta(days=1)
                continue
            if stock.ipo_date and current < stock.ipo_date:
                current += timedelta(days=1)
                continue

            susp = session.get(StockSuspension, {"symbol": item.symbol, "trade_date": current})
            if susp and not susp.resolved_at:
                current += timedelta(days=1)
                continue

            kline = session.get(
                KlineDay,
                {"symbol": item.symbol, "trade_date": current, "adjust_flag": item.adjust_flag},
            )
            if not kline:
                qcr = QualityCheckResult(
                    job_id=job_id,
                    job_item_id=item.id,
                    symbol=item.symbol,
                    frequency=item.frequency,
                    adjust_flag=item.adjust_flag,
                    start_date=current,
                    end_date=current,
                    check_type="missing_kline",
                    severity="error",
                    status="open",
                    message=f"Missing kline for {item.symbol} on {current}",
                )
                session.add(qcr)
                item.status = "failed"
                item.error_message = f"Missing kline on {current}"
                issues += 1
            else:
                issues += _validate_kline_row(session, kline, item, job_id)

            current += timedelta(days=1)

    session.flush()
    finalize_job(session, job)
    session.commit()
    return issues


def _check_kline_ohlc(session: Session, item: CollectJobItem, job_id: int) -> int:
    from collector.kline_table_router import get_kline_model

    model = get_kline_model(item.frequency)
    rows = session.scalars(
        select(model).where(
            model.symbol == item.symbol,
            model.adjust_flag == item.adjust_flag,
            model.trade_date >= item.start_date,
            model.trade_date <= item.end_date,
        )
    ).all()
    issues = 0
    for row in rows:
        issues += _validate_kline_row(session, row, item, job_id)
    return issues


def _validate_kline_row(session: Session, kline, item: CollectJobItem, job_id: int) -> int:
    issues = 0
    o, h, low, c = kline.open, kline.high, kline.low, kline.close
    if o is not None and h is not None and low is not None and c is not None:
        if h < low or h < o or h < c or low > o or low > c:
            session.add(
                QualityCheckResult(
                    job_id=job_id,
                    job_item_id=item.id,
                    symbol=item.symbol,
                    frequency=item.frequency,
                    adjust_flag=item.adjust_flag,
                    start_date=kline.trade_date,
                    end_date=kline.trade_date,
                    check_type="invalid_ohlc",
                    severity="error",
                    status="open",
                    message="Invalid OHLC relationship",
                    sample_payload={"open": str(o), "high": str(h), "low": str(low), "close": str(c)},
                )
            )
            item.status = "failed"
            issues += 1

    if kline.volume is not None and kline.volume < 0:
        session.add(
            QualityCheckResult(
                job_id=job_id,
                job_item_id=item.id,
                symbol=item.symbol,
                check_type="negative_volume",
                severity="error",
                status="open",
                message="Negative volume",
            )
        )
        item.status = "failed"
        issues += 1

    return issues


def resolve_quality_checks(
    session: Session,
    symbol: str,
    frequency: str,
    adjust_flag: str | None,
    start_date: date | None,
    end_date: date | None,
):
    conditions = [
        QualityCheckResult.symbol == symbol,
        QualityCheckResult.frequency == frequency,
        QualityCheckResult.status == "open",
    ]
    if adjust_flag:
        conditions.append(QualityCheckResult.adjust_flag == adjust_flag)
    if start_date and end_date:
        conditions.append(
            and_(
                QualityCheckResult.start_date.isnot(None),
                QualityCheckResult.start_date <= end_date,
                or_(
                    QualityCheckResult.end_date.is_(None),
                    QualityCheckResult.end_date >= start_date,
                ),
            )
        )

    checks = session.scalars(select(QualityCheckResult).where(*conditions)).all()
    now = datetime.now(timezone.utc)
    for check in checks:
        check.status = "resolved"
        check.resolved_at = now
        check.resolved_reason = "recollected"
