from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.symbol import SymbolOut
from app.services.symbol_query_service import SymbolQueryService

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


@router.get("", response_model=list[SymbolOut])
def list_symbols(
    board: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    include_excluded: bool = Query(False),
    db: Session = Depends(get_db),
):
    return SymbolQueryService(db).query_symbols(board, status, keyword, include_excluded)
