import logging
from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import IndustryBoard, StockIndustryBoard, StockMaster
from collector.industry_board_clients import (
    IndustryBoardFetchError,
    fetch_sw_boards,
    fetch_sw_constituents,
    fetch_ths_boards,
    fetch_ths_constituents,
    sleep_quietly,
)
from collector.industry_board_utils import pinyin_initial
from collector.job_helper import create_job, finalize_job

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_SLEEP_SECONDS = 0.35
# Require at least this many memberships for THS to be considered successful.
MIN_THS_MEMBERSHIPS = 100


def sync_industry_boards(
    session: Session,
    snapshot_date: date,
    *,
    sleep_seconds: float = DEFAULT_REQUEST_SLEEP_SECONDS,
    source: str = "auto",
) -> tuple[int, int, str]:
    """Sync industry boards and memberships.

    source: auto | ths | sw
    Returns (board_count, member_count, used_source).
    """
    job = create_job(
        session,
        "sync_industry_boards",
        params={"snapshot_date": str(snapshot_date), "requested_source": source},
    )
    session.commit()

    try:
        used_source, board_rows, membership = _load_boards_and_members(
            session,
            snapshot_date,
            source=source,
            sleep_seconds=sleep_seconds,
        )

        active_count = session.scalar(
            select(func.count()).select_from(StockMaster).where(StockMaster.status == "active")
        ) or 0
        existing_count = session.scalar(select(func.count()).select_from(StockIndustryBoard)) or 0
        # Never wipe a populated mapping with an empty fetch result.
        if active_count > 0 and existing_count > 0 and len(membership) == 0:
            raise IndustryBoardFetchError(
                f"Refusing to replace {existing_count} industry memberships with empty result "
                f"(source={used_source}, boards={len(board_rows)}, active_stocks={active_count})"
            )

        # Clear memberships first (FK to industry_board).
        session.execute(delete(StockIndustryBoard))
        session.flush()

        keep_codes = {b["board_code"] for b in board_rows}
        stale_boards = session.scalars(
            select(IndustryBoard).where(IndustryBoard.board_code.not_in(keep_codes))
        ).all()
        for stale in stale_boards:
            session.delete(stale)
        session.flush()

        for board in board_rows:
            stmt = insert(IndustryBoard).values(**board)
            stmt = stmt.on_conflict_do_update(
                index_elements=["board_code"],
                set_={
                    "board_name": board["board_name"],
                    "pinyin_initial": board["pinyin_initial"],
                    "source": board["source"],
                    "snapshot_date": board["snapshot_date"],
                    "raw_payload": board["raw_payload"],
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            session.execute(stmt)
        session.flush()

        for member in membership.values():
            session.add(StockIndustryBoard(**member))

        job.params = {
            **(job.params or {}),
            "used_source": used_source,
            "board_count": len(board_rows),
            "member_count": len(membership),
        }

        finalize_job(
            session,
            job,
            inserted_rows=len(membership),
            updated_rows=len(board_rows),
        )
        session.commit()
        return len(board_rows), len(membership), used_source
    except Exception as e:
        session.rollback()
        failed = session.get(type(job), job.id)
        if failed:
            failed.status = "failed"
            failed.error_message = str(e)
            failed.finished_at = datetime.now(timezone.utc)
            session.commit()
        raise


def _load_boards_and_members(
    session: Session,
    snapshot_date: date,
    *,
    source: str,
    sleep_seconds: float,
) -> tuple[str, list[dict], dict[str, dict]]:
    source = (source or "auto").lower()
    if source not in {"auto", "ths", "sw"}:
        raise ValueError("source must be one of: auto, ths, sw")

    active_symbols = set(
        session.scalars(select(StockMaster.symbol).where(StockMaster.status == "active")).all()
    )

    if source in {"auto", "ths"}:
        try:
            board_rows, membership = _fetch_from_ths(snapshot_date, active_symbols, sleep_seconds)
            if source == "ths" or len(membership) >= MIN_THS_MEMBERSHIPS:
                return "ths", board_rows, membership
            logger.warning(
                "THS memberships too few (%s < %s), falling back to Shenwan",
                len(membership),
                MIN_THS_MEMBERSHIPS,
            )
        except Exception as e:
            if source == "ths":
                raise
            logger.warning("THS industry sync failed, falling back to Shenwan: %s", e)

    board_rows, membership = _fetch_from_sw(snapshot_date, active_symbols, sleep_seconds)
    return "sw", board_rows, membership


def _fetch_from_ths(
    snapshot_date: date,
    active_symbols: set[str],
    sleep_seconds: float,
) -> tuple[list[dict], dict[str, dict]]:
    boards = fetch_ths_boards()
    board_rows: list[dict] = []
    membership: dict[str, dict] = {}
    failures = 0

    for board in boards:
        board_rows.append(
            {
                "board_code": board["board_code"],
                "board_name": board["board_name"],
                "pinyin_initial": pinyin_initial(board["board_name"]),
                "source": "ths",
                "snapshot_date": snapshot_date,
                "raw_payload": board["raw"],
            }
        )

    for board in boards:
        try:
            symbols = fetch_ths_constituents(board["source_code"])
        except IndustryBoardFetchError as e:
            failures += 1
            logger.warning("%s", e)
            sleep_quietly(sleep_seconds)
            continue

        for symbol in symbols:
            if symbol not in active_symbols:
                continue
            membership.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "board_code": board["board_code"],
                    "board_name": board["board_name"],
                    "source": "ths",
                    "snapshot_date": snapshot_date,
                },
            )
        sleep_quietly(sleep_seconds)

    if not board_rows:
        raise IndustryBoardFetchError("THS returned no boards")
    if failures == len(boards):
        raise IndustryBoardFetchError("THS constituent fetch failed for all boards")
    return board_rows, membership


def _fetch_from_sw(
    snapshot_date: date,
    active_symbols: set[str],
    sleep_seconds: float,
) -> tuple[list[dict], dict[str, dict]]:
    boards = fetch_sw_boards()
    board_rows: list[dict] = []
    membership: dict[str, dict] = {}
    failures = 0

    for board in boards:
        board_rows.append(
            {
                "board_code": board["board_code"],
                "board_name": board["board_name"],
                "pinyin_initial": pinyin_initial(board["board_name"]),
                "source": "sw",
                "snapshot_date": snapshot_date,
                "raw_payload": board["raw"],
            }
        )

    for board in boards:
        try:
            symbols = fetch_sw_constituents(board["source_code"])
        except IndustryBoardFetchError as e:
            failures += 1
            logger.warning("%s", e)
            sleep_quietly(sleep_seconds)
            continue

        for symbol in symbols:
            if symbol not in active_symbols:
                continue
            membership.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "board_code": board["board_code"],
                    "board_name": board["board_name"],
                    "source": "sw",
                    "snapshot_date": snapshot_date,
                },
            )
        sleep_quietly(sleep_seconds)

    if not board_rows:
        raise IndustryBoardFetchError("Shenwan returned no boards")
    if failures == len(boards):
        raise IndustryBoardFetchError("Shenwan constituent fetch failed for all boards")
    if not membership and active_symbols:
        # Still allow empty membership when stock_master is empty (fresh install).
        logger.warning("Shenwan returned no memberships matching active stocks")
    return board_rows, membership
