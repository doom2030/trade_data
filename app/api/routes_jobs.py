from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.job import (
    JobItemOut,
    JobItemRetryRequest,
    JobOut,
    JobRetryRequest,
    JobRetryResponse,
)
from app.services.job_command_service import JobCommandService
from app.services.job_query_service import JobQueryService

router = APIRouter(prefix="/api", tags=["jobs"])

MAX_JOBS_LIMIT = 200
MAX_JOB_ITEMS_LIMIT = 500


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    status: str | None = None,
    job_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_JOBS_LIMIT),
    db: Session = Depends(get_db),
):
    return JobQueryService(db).list_jobs(
        status, job_type, limit, offset=offset, date_from=date_from, date_to=date_to
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = JobQueryService(db).get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs/{job_id}/items", response_model=list[JobItemOut])
def list_job_items(
    job_id: int,
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=MAX_JOB_ITEMS_LIMIT),
    db: Session = Depends(get_db),
):
    return JobQueryService(db).list_job_items(job_id, status, offset, limit)


@router.post("/jobs/{job_id}/retry", response_model=JobRetryResponse)
def retry_job(
    job_id: int,
    req: JobRetryRequest,
    db: Session = Depends(get_db),
):
    return JobCommandService(db).retry_job(job_id, req.only_failed_items, req.max_attempts)


@router.post("/job-items/{item_id}/retry", response_model=JobRetryResponse)
def retry_item(
    item_id: int,
    req: JobItemRetryRequest,
    db: Session = Depends(get_db),
):
    return JobCommandService(db).retry_item(item_id, req.max_attempts)
