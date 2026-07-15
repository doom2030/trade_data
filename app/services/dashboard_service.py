from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import CollectJob, KlineDay, StockMaster, TradeCalendar


class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    def _estimate_table_rows(self, table_name: str) -> int | None:
        estimate = self.db.scalar(
            text(
                """
                SELECT GREATEST(COALESCE(s.n_live_tup::double precision, c.reltuples, 0), 0)::bigint
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
                WHERE n.nspname = 'public' AND c.relname = :table_name
                """
            ),
            {"table_name": table_name},
        )
        return int(estimate) if estimate is not None else None

    def get_stats(self) -> dict:
        active_count = self.db.scalar(
            select(func.count()).select_from(StockMaster).where(StockMaster.status == "active")
        ) or 0
        excluded_count = self.db.scalar(
            select(func.count()).select_from(StockMaster).where(StockMaster.status == "excluded")
        ) or 0
        kline_count = self._estimate_table_rows(KlineDay.__tablename__)
        kline_rows_estimated = kline_count is not None
        if kline_count is None:
            kline_count = self.db.scalar(select(func.count()).select_from(KlineDay)) or 0
        pending_jobs = self.db.scalar(
            select(func.count()).select_from(CollectJob).where(CollectJob.status == "pending")
        ) or 0
        failed_jobs = self.db.scalar(
            select(func.count()).select_from(CollectJob).where(CollectJob.status == "failed")
        ) or 0
        trading_days = self.db.scalar(
            select(func.count()).select_from(TradeCalendar).where(TradeCalendar.is_trading_day.is_(True))
        ) or 0

        recent_jobs = self.db.scalars(
            select(CollectJob).order_by(CollectJob.created_at.desc()).limit(8)
        ).all()

        return {
            "active_stocks": active_count,
            "excluded_stocks": excluded_count,
            "kline_rows": kline_count,
            "kline_rows_estimated": kline_rows_estimated,
            "pending_jobs": pending_jobs,
            "failed_jobs": failed_jobs,
            "trading_days": trading_days,
            "recent_jobs": recent_jobs,
        }
