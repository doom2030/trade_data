from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CollectJob, StockMaster
from app.schemas.job import JobRetryResponse
from app.schemas.kline import BackfillRequest, BackfillResponse
from collector.kline_sync import manual_backfill
from collector.retry_service import retry_failed_item, retry_failed_job

settings = get_settings()


class JobCommandService:
    def __init__(self, db: Session):
        self.db = db

    def retry_job(self, job_id: int, only_failed: bool = True, max_attempts: int = 3) -> JobRetryResponse:
        existing = self.db.scalars(
            select(CollectJob).where(
                CollectJob.retry_of_job_id == job_id,
                CollectJob.status.in_(["pending", "running"]),
            )
        ).first()
        if existing:
            return JobRetryResponse(
                job_id=existing.id,
                status=existing.status,
                job_type=existing.job_type,
                retry_of_job_id=existing.retry_of_job_id,
            )

        try:
            job = retry_failed_job(self.db, job_id, only_failed, max_attempts)
        except ValueError as e:
            if "not found" in str(e).lower():
                raise HTTPException(404, str(e)) from e
            raise HTTPException(400, str(e)) from e
        return JobRetryResponse(
            job_id=job.id,
            status=job.status,
            job_type=job.job_type,
            retry_of_job_id=job.retry_of_job_id,
        )

    def retry_item(self, item_id: int, max_attempts: int = 3) -> JobRetryResponse:
        try:
            job = retry_failed_item(self.db, item_id, max_attempts)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return JobRetryResponse(
            job_id=job.id,
            status=job.status,
            job_type=job.job_type,
            retry_of_item_id=job.retry_of_item_id,
        )

    def create_backfill(self, req: BackfillRequest) -> BackfillResponse:
        stock = self.db.get(StockMaster, req.symbol)
        if not stock:
            raise HTTPException(404, "Symbol not found")
        if stock.status != "active":
            raise HTTPException(400, "Only active stocks can be backfilled")

        if req.frequency not in ("day", "week", "month"):
            raise HTTPException(400, "Invalid frequency")

        if req.end < req.start:
            raise HTTPException(400, "end must be >= start")

        days = (req.end - req.start).days + 1
        if days < 1:
            raise HTTPException(400, "Invalid date range")
        if days > settings.manual_backfill_max_natural_days:
            raise HTTPException(
                400,
                f"Date range exceeds max {settings.manual_backfill_max_natural_days} natural days",
            )

        pending_jobs = self.db.scalars(
            select(CollectJob).where(
                CollectJob.job_type == "manual_backfill_range",
                CollectJob.status.in_(["pending", "running"]),
                CollectJob.start_date == req.start,
                CollectJob.end_date == req.end,
                CollectJob.frequency == req.frequency,
            )
        ).all()
        existing = next(
            (j for j in pending_jobs if (j.params or {}).get("symbol") == req.symbol),
            None,
        )
        if existing:
            return BackfillResponse(
                job_id=existing.id,
                status=existing.status,
                job_type=existing.job_type,
                symbol=req.symbol,
                frequency=req.frequency,
                start=req.start.isoformat(),
                end=req.end.isoformat(),
                adjust_flags=settings.adjust_flags,
            )

        job = manual_backfill(self.db, req.symbol, req.frequency, req.start, req.end)
        return BackfillResponse(
            job_id=job.id,
            status=job.status,
            job_type=job.job_type,
            symbol=req.symbol,
            frequency=req.frequency,
            start=req.start.isoformat(),
            end=req.end.isoformat(),
            adjust_flags=settings.adjust_flags,
        )
