from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.kline import BackfillRequest, BackfillResponse, KlineResponse
from app.services.job_command_service import JobCommandService
from app.services.kline_query_service import KlineQueryService

router = APIRouter(prefix="/api", tags=["klines"])


@router.get("/klines/{frequency}", response_model=KlineResponse)
def get_klines(
    frequency: str,
    symbol: str = Query(...),
    start: date = Query(...),
    end: date = Query(...),
    adjust: str = Query("forward"),
    db: Session = Depends(get_db),
):
    return KlineQueryService(db).query_klines(frequency, symbol, start, end, adjust)


@router.post("/klines/backfill", response_model=BackfillResponse)
def backfill_klines(req: BackfillRequest, db: Session = Depends(get_db)):
    return JobCommandService(db).create_backfill(req)
