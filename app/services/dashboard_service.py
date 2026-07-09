from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CollectJob, KlineDay, StockMaster, TradeCalendar


class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    def get_stats(self) -> dict:
        active_count = self.db.scalar(
            select(func.count()).select_from(StockMaster).where(StockMaster.status == "active")
        ) or 0
        excluded_count = self.db.scalar(
            select(func.count()).select_from(StockMaster).where(StockMaster.status == "excluded")
        ) or 0
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
            "pending_jobs": pending_jobs,
            "failed_jobs": failed_jobs,
            "trading_days": trading_days,
            "recent_jobs": recent_jobs,
        }
