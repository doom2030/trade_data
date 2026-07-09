from datetime import date, datetime

from pydantic import BaseModel, Field


class JobOut(BaseModel):
    id: int
    job_type: str
    status: str
    frequency: str | None = None
    adjust_flag: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    target_trade_date: date | None = None
    total_items: int = 0
    success_items: int = 0
    failed_items: int = 0
    skipped_items: int = 0
    exhausted_items: int = 0
    compensated_items: int = 0
    inserted_rows: int = 0
    updated_rows: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class JobItemOut(BaseModel):
    id: int
    job_id: int
    symbol: str | None = None
    frequency: str | None = None
    adjust_flag: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str
    attempt_count: int = 0
    inserted_rows: int = 0
    updated_rows: int = 0
    error_code: str | None = None
    error_message: str | None = None
    retry_of_item_id: int | None = None

    model_config = {"from_attributes": True}


class JobRetryRequest(BaseModel):
    only_failed_items: bool = True
    max_attempts: int = Field(default=3, ge=1, le=15)


class JobItemRetryRequest(BaseModel):
    max_attempts: int = Field(default=3, ge=1, le=15)


class JobRetryResponse(BaseModel):
    job_id: int
    status: str
    job_type: str
    retry_of_job_id: int | None = None
    retry_of_item_id: int | None = None
