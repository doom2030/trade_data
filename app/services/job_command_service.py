from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CollectJob, CollectJobItem, CollectJobLog, QualityCheckResult, StockMaster
from app.schemas.job import JobRetryResponse
from app.schemas.kline import BackfillRequest, BackfillResponse
from collector.job_helper import create_job
from collector.kline_sync import (
    create_catchup_jobs,
    get_missed_trading_days,
    manual_backfill,
)
from collector.retry_service import retry_failed_item, retry_failed_job

settings = get_settings()


def _required(params: dict, key: str):
    value = params.get(key)
    if value in (None, ""):
        raise HTTPException(400, f"Missing required parameter: {key}")
    return value


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

    def delete_jobs(self, job_ids: list[int]) -> int:
        ids = sorted({int(job_id) for job_id in job_ids if int(job_id) > 0})
        if not ids:
            raise HTTPException(400, "No jobs selected")

        running = self.db.scalars(
            select(CollectJob.id).where(
                CollectJob.id.in_(ids),
                CollectJob.status == "running",
            )
        ).all()
        if running:
            raise HTTPException(400, f"Cannot delete running jobs: {', '.join(str(i) for i in running)}")

        existing_ids = self.db.scalars(select(CollectJob.id).where(CollectJob.id.in_(ids))).all()
        if not existing_ids:
            raise HTTPException(404, "No matching jobs found")

        item_ids = self.db.scalars(
            select(CollectJobItem.id).where(CollectJobItem.job_id.in_(existing_ids))
        ).all()

        self.db.execute(
            update(CollectJob)
            .where(CollectJob.retry_of_job_id.in_(existing_ids))
            .values(retry_of_job_id=None)
        )
        if item_ids:
            self.db.execute(
                update(CollectJob)
                .where(CollectJob.retry_of_item_id.in_(item_ids))
                .values(retry_of_item_id=None)
            )
            self.db.execute(delete(QualityCheckResult).where(QualityCheckResult.job_item_id.in_(item_ids)))

        self.db.execute(delete(QualityCheckResult).where(QualityCheckResult.job_id.in_(existing_ids)))
        self.db.execute(delete(CollectJobLog).where(CollectJobLog.job_id.in_(existing_ids)))
        self.db.execute(delete(CollectJobItem).where(CollectJobItem.job_id.in_(existing_ids)))
        self.db.execute(delete(CollectJob).where(CollectJob.id.in_(existing_ids)))
        self.db.commit()
        return len(existing_ids)

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

    def trigger_job(self, action: str, params: dict) -> CollectJob | list[int] | int:
        action = action.strip()

        if action == "manual_backfill_range":
            req = BackfillRequest(
                symbol=_required(params, "symbol"),
                frequency=_required(params, "frequency"),
                start=_required(params, "start"),
                end=_required(params, "end"),
            )
            return self.create_backfill(req).job_id

        if action == "catchup_daily_update":
            missed = get_missed_trading_days(self.db, _required(params, "up_to"))
            if not missed:
                raise HTTPException(400, "No missed trading days found")
            return create_catchup_jobs(self.db, missed)

        if action == "quality_check":
            job_id = int(_required(params, "job_id"))
            if not self.db.get(CollectJob, job_id):
                raise HTTPException(404, "Job not found")
            return self._enqueue_job("quality_check", params={"target_job_id": job_id})

        if action == "sync_stock_meta":
            return self._enqueue_job(
                "sync_stock_meta",
                params={"snapshot_date": _required(params, "snapshot_date").isoformat()},
            )
        if action == "sync_industry":
            return self._enqueue_job(
                "sync_industry",
                params={"snapshot_date": _required(params, "snapshot_date").isoformat()},
            )
        if action == "sync_industry_boards":
            return self._enqueue_job(
                "sync_industry_boards",
                params={
                    "snapshot_date": _required(params, "snapshot_date").isoformat(),
                    "source": _required(params, "source"),
                    "sleep_seconds": float(_required(params, "sleep_seconds")),
                },
            )
        if action == "sync_trade_calendar":
            return self._enqueue_job(
                "sync_trade_calendar",
                start_date=_required(params, "start"),
                end_date=_required(params, "end"),
                params={
                    "start": _required(params, "start").isoformat(),
                    "end": _required(params, "end").isoformat(),
                },
            )
        if action == "daily_update":
            trade_date = _required(params, "trade_date")
            return self._enqueue_job(
                "daily_update",
                frequency="day",
                target_trade_date=trade_date,
                params={"trade_date": trade_date.isoformat()},
            )
        if action == "update_weekly":
            end_date = _required(params, "end_date")
            return self._enqueue_job(
                "update_weekly",
                frequency="week",
                end_date=end_date,
                params={"end_date": end_date.isoformat()},
            )
        if action == "update_monthly":
            end_date = _required(params, "end_date")
            return self._enqueue_job(
                "update_monthly",
                frequency="month",
                end_date=end_date,
                params={"end_date": end_date.isoformat()},
            )
        if action == "retry_failed_jobs":
            return self._enqueue_job(
                "retry_failed_jobs",
                params={
                    "max_attempts": int(_required(params, "max_attempts")),
                    "limit": int(_required(params, "limit")),
                },
            )

        raise HTTPException(400, "Unsupported job action")

    def _enqueue_job(
        self,
        job_type: str,
        *,
        frequency: str | None = None,
        start_date=None,
        end_date=None,
        target_trade_date=None,
        params: dict | None = None,
    ) -> CollectJob:
        job = create_job(
            self.db,
            job_type,
            frequency=frequency,
            start_date=start_date,
            end_date=end_date,
            target_trade_date=target_trade_date,
            params=params,
            status="pending",
        )
        self.db.commit()
        return job
