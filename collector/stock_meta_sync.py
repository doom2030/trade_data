import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import CollectJob, StockMaster, StockStatusHistory
from collector.baostock_client import BaostockClient
from collector.board_classifier import classify_board, is_st_name, parse_symbol
from collector.job_helper import create_job, finalize_job

logger = logging.getLogger(__name__)


def _is_delisted(out_date: date | None, snapshot_date: date) -> bool:
    return bool(out_date and out_date <= snapshot_date)


def sync_stock_meta(
    session: Session,
    client: BaostockClient,
    snapshot_date: date,
    job: CollectJob | None = None,
) -> int:
    job = job or create_job(session, "sync_stock_meta", params={"snapshot_date": str(snapshot_date)})
    session.commit()

    try:
        rows = client.query_stock_basic(snapshot_date)
        upserted = 0
        for row in rows:
            parsed = parse_symbol(row.get("code", ""))
            if not parsed:
                continue
            symbol, exchange, code = parsed
            name = row.get("code_name") or ""
            board = classify_board(symbol)
            ipo_date = row.get("ipo_date")
            out_date = row.get("out_date")

            if board is None:
                logger.debug("Skip out-of-scope symbol: %s", symbol)
                continue
            if is_st_name(name):
                _handle_status_change(
                    session, symbol, exchange, code, name, board, "excluded", "st_name",
                    snapshot_date, row, ipo_date, out_date,
                )
                upserted += 1
                continue
            if _is_delisted(out_date, snapshot_date):
                _handle_status_change(
                    session, symbol, exchange, code, name, board, "inactive", "delisted",
                    snapshot_date, row, ipo_date, out_date,
                )
                upserted += 1
                continue

            existing = session.get(StockMaster, symbol)
            if existing and existing.status in ("excluded", "inactive"):
                _reactivate_stock(session, existing, snapshot_date, "recovered")

            stmt = insert(StockMaster).values(
                symbol=symbol,
                exchange=exchange,
                code=code,
                name=name,
                board=board,
                ipo_date=ipo_date,
                out_date=out_date,
                status="active",
                security_type="stock",
                source="baostock",
                raw_payload=row.get("raw_payload"),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol"],
                set_={
                    "name": name,
                    "board": board,
                    "ipo_date": ipo_date,
                    "out_date": out_date,
                    "status": "active",
                    "raw_payload": row.get("raw_payload"),
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            session.execute(stmt)

            if not existing:
                _add_status_history(session, symbol, "active", "new_listing", snapshot_date)

            upserted += 1

        finalize_job(session, job, inserted_rows=upserted)
        session.commit()
        return upserted
    except Exception as e:
        job.status = "failed"
        job.error_message = str(e)
        job.finished_at = datetime.now(timezone.utc)
        session.commit()
        raise


def _handle_status_change(
    session, symbol, exchange, code, name, board, new_status, reason, snapshot_date, row,
    ipo_date=None, out_date=None,
):
    existing = session.get(StockMaster, symbol)
    if existing:
        if existing.status != new_status:
            _close_current_history(session, symbol, snapshot_date)
            _add_status_history(session, symbol, new_status, reason, snapshot_date)
        existing.name = name
        existing.status = new_status
        existing.ipo_date = ipo_date or existing.ipo_date
        existing.out_date = out_date or existing.out_date
        existing.raw_payload = row.get("raw_payload")
        existing.updated_at = datetime.now(timezone.utc)
    else:
        session.add(
            StockMaster(
                symbol=symbol,
                exchange=exchange,
                code=code,
                name=name,
                board=board,
                ipo_date=ipo_date,
                out_date=out_date,
                status=new_status,
                raw_payload=row.get("raw_payload"),
            )
        )
        _add_status_history(session, symbol, new_status, reason, snapshot_date)


def _reactivate_stock(session, stock: StockMaster, snapshot_date: date, reason: str):
    _close_current_history(session, stock.symbol, snapshot_date)
    stock.status = "active"
    _add_status_history(session, stock.symbol, "active", reason, snapshot_date)


def _close_current_history(session, symbol: str, valid_to: date):
    open_hist = session.scalars(
        select(StockStatusHistory).where(
            StockStatusHistory.symbol == symbol,
            StockStatusHistory.valid_to.is_(None),
        )
    ).first()
    if open_hist:
        open_hist.valid_to = valid_to


def _add_status_history(session, symbol: str, status: str, reason: str, valid_from: date):
    session.add(
        StockStatusHistory(
            symbol=symbol,
            status=status,
            reason=reason,
            valid_from=valid_from,
        )
    )
