import hashlib
import logging
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


def _lock_id(key: str) -> int:
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _lock_class_obj(lock_id: int) -> tuple[int, int]:
    """Split signed bigint advisory key the way PostgreSQL stores it in pg_locks."""
    unsigned = lock_id % (1 << 64)
    return (unsigned >> 32) & 0xFFFFFFFF, unsigned & 0xFFFFFFFF


def _bind_engine(session: Session) -> Engine:
    bind = session.get_bind()
    if isinstance(bind, Engine):
        return bind
    return bind.engine


def collect_lock_holders(session: Session) -> list[dict]:
    """Return sessions currently holding the collect advisory lock."""
    lock_id = _lock_id(settings.collect_global_lock_key)
    classid, objid = _lock_class_obj(lock_id)
    rows = session.execute(
        text(
            """
            SELECT a.pid,
                   a.state,
                   a.application_name,
                   a.query_start,
                   left(a.query, 160) AS query
            FROM pg_locks l
            JOIN pg_stat_activity a ON a.pid = l.pid
            WHERE l.locktype = 'advisory'
              AND l.granted = true
              AND l.classid = :classid
              AND l.objid = :objid
              AND l.objsubid = 1
            """
        ),
        {"classid": classid, "objid": objid},
    ).mappings().all()
    return [dict(r) for r in rows]


def format_lock_contention_message(session: Session | None = None) -> str:
    base = (
        "无法获取采集锁（同一时间只允许一个 baostock 采集进程）。"
        "若 pending-worker 日志也在反复 Failed to acquire collect lock，"
        "多半是连接池泄漏了会话级锁：请重建镜像后执行 "
        "`python scripts/check_collect_lock.py --release`。"
    )
    if session is None:
        return base
    try:
        holders = collect_lock_holders(session)
    except Exception:
        return base
    if not holders:
        return base
    parts = []
    for h in holders[:3]:
        parts.append(
            f"pid={h.get('pid')} state={h.get('state')} app={h.get('application_name') or '-'}"
        )
    return base + " 持锁进程: " + "; ".join(parts)


def release_collect_lock_holders(session: Session) -> list[int]:
    """Terminate backends holding the collect lock (recovery for leaked locks)."""
    holders = collect_lock_holders(session)
    released: list[int] = []
    for h in holders:
        pid = h.get("pid")
        if pid is None:
            continue
        ok = session.execute(
            text("SELECT pg_terminate_backend(:pid)"),
            {"pid": int(pid)},
        ).scalar()
        if ok:
            released.append(int(pid))
            logger.warning("Terminated backend pid=%s holding collect lock", pid)
    session.commit()
    return released


def _try_lock(conn: Connection, lock_id: int) -> bool:
    return bool(conn.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id}).scalar())


def _lock_blocking(conn: Connection, lock_id: int, timeout_seconds: int | None) -> bool:
    if timeout_seconds is not None and timeout_seconds > 0:
        conn.execute(
            text("SET lock_timeout = :timeout"),
            {"timeout": f"{int(timeout_seconds)}s"},
        )
    try:
        conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": lock_id})
        return True
    except Exception:
        logger.warning(
            "Timed out or failed waiting for collect lock (key=%s)",
            settings.collect_global_lock_key,
        )
        return False
    finally:
        if timeout_seconds is not None and timeout_seconds > 0:
            conn.execute(text("SET lock_timeout = 0"))


@contextmanager
def acquire_collect_lock(
    session: Session,
    wait: bool = False,
    timeout_seconds: int | None = None,
):
    """Acquire PostgreSQL advisory lock for baostock collection.

    Uses a *dedicated* engine connection held for the whole critical section.
    Session-level advisory locks must not go through the SQLAlchemy Session
    pool directly: commit/checkout can move later unlocks onto another
    connection and permanently leak the lock (exactly the pending-worker loop).
    """
    lock_id = _lock_id(settings.collect_global_lock_key)
    engine = _bind_engine(session)
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    acquired = False

    try:
        if wait:
            acquired = _lock_blocking(conn, lock_id, timeout_seconds)
        else:
            acquired = _try_lock(conn, lock_id)

        if not acquired:
            logger.warning(
                "Failed to acquire collect lock (key=%s)",
                settings.collect_global_lock_key,
            )
            yield False
            return

        logger.info("Acquired collect lock (key=%s)", settings.collect_global_lock_key)
        yield True
    finally:
        if acquired:
            try:
                conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
                logger.info("Released collect lock")
            except Exception:
                logger.exception("Failed to unlock collect lock; discarding connection")
                conn.invalidate()
        conn.close()
