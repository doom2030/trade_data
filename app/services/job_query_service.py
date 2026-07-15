from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CollectJob, CollectJobItem, CollectJobLog
from app.schemas.job import JobItemOut, JobLogOut, JobOut

# Align date filters with UI display timezone (Asia/Shanghai).
_FILTER_TZ = ZoneInfo("Asia/Shanghai")


class JobQueryService:
    MAX_JOBS_LIMIT = 200
    MAX_JOB_ITEMS_LIMIT = 500

    def __init__(self, db: Session):
        self.db = db

    def list_jobs(
        self,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[JobOut]:
        limit = min(max(limit, 1), self.MAX_JOBS_LIMIT)
        offset = max(offset, 0)
        query = self._jobs_query(status, job_type, date_from, date_to)
        query = query.order_by(CollectJob.created_at.desc()).offset(offset).limit(limit)
        jobs = self.db.scalars(query).all()
        return [JobOut.model_validate(j) for j in jobs]

    def count_jobs(
        self,
        status: str | None = None,
        job_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> int:
        query = self._jobs_query(status, job_type, date_from, date_to)
        return self.db.scalar(select(func.count()).select_from(query.subquery())) or 0

    def _jobs_query(
        self,
        status: str | None = None,
        job_type: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ):
        query = select(CollectJob)
        if status:
            query = query.where(CollectJob.status == status)
        if job_type:
            query = query.where(CollectJob.job_type == job_type)
        if date_from:
            start = datetime(
                date_from.year, date_from.month, date_from.day, tzinfo=_FILTER_TZ
            )
            query = query.where(CollectJob.created_at >= start)
        if date_to:
            end = datetime(
                date_to.year, date_to.month, date_to.day, tzinfo=_FILTER_TZ
            ) + timedelta(days=1)
            query = query.where(CollectJob.created_at < end)
        return query

    def get_job(self, job_id: int) -> JobOut | None:
        job = self.db.get(CollectJob, job_id)
        if not job:
            return None
        return JobOut.model_validate(job)

    def list_job_items(
        self,
        job_id: int,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[JobItemOut]:
        limit = min(max(limit, 1), self.MAX_JOB_ITEMS_LIMIT)
        offset = max(offset, 0)
        query = select(CollectJobItem).where(CollectJobItem.job_id == job_id)
        if status:
            query = query.where(CollectJobItem.status == status)
        query = query.order_by(CollectJobItem.id).offset(offset).limit(limit)
        items = self.db.scalars(query).all()
        return [self._to_job_item_out(i) for i in items]

    def count_job_items(self, job_id: int, status: str | None = None) -> int:
        query = select(func.count()).select_from(CollectJobItem).where(CollectJobItem.job_id == job_id)
        if status:
            query = query.where(CollectJobItem.status == status)
        return self.db.scalar(query) or 0

    def list_job_logs(self, job_id: int, limit: int = 200) -> list[JobLogOut]:
        limit = min(max(limit, 1), 500)
        logs = self.db.scalars(
            select(CollectJobLog)
            .where(CollectJobLog.job_id == job_id)
            .order_by(CollectJobLog.id.desc())
            .limit(limit)
        ).all()
        return [JobLogOut.model_validate(log) for log in reversed(logs)]

    @staticmethod
    def _to_job_item_out(item: CollectJobItem) -> JobItemOut:
        out = JobItemOut.model_validate(item)
        retry_of_item_id = (item.params or {}).get("retry_of_item_id")
        if retry_of_item_id is not None:
            return out.model_copy(update={"retry_of_item_id": int(retry_of_item_id)})
        return out
