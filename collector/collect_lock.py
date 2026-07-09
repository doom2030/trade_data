import hashlib
import logging
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


def _lock_id(key: str) -> int:
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@contextmanager
def acquire_collect_lock(session: Session, wait: bool = False):
    """Acquire PostgreSQL advisory lock for baostock collection."""
    lock_id = _lock_id(settings.collect_global_lock_key)
    if wait:
        session.execute(text("SELECT pg_advisory_lock(:id)"), {"id": lock_id})
        acquired = True
    else:
        result = session.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id})
        acquired = result.scalar()

    if not acquired:
        logger.warning("Failed to acquire collect lock (key=%s)", settings.collect_global_lock_key)
        yield False
        return

    logger.info("Acquired collect lock (key=%s)", settings.collect_global_lock_key)
    try:
        yield True
    finally:
        session.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
        logger.info("Released collect lock")
