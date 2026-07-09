from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.symbol import IndustryGroupedOut, IndustryOut, IndustrySymbolOut
from app.services.industry_query_service import IndustryQueryService

router = APIRouter(prefix="/api/industries", tags=["industries"])


@router.get("", response_model=list[IndustryOut] | IndustryGroupedOut)
def list_industries(
    grouped: bool = Query(False),
    db: Session = Depends(get_db),
):
    service = IndustryQueryService(db)
    if grouped:
        return IndustryGroupedOut(groups=service.list_industries_grouped())
    return service.list_industries()


@router.get("/{industry_name}/symbols", response_model=list[IndustrySymbolOut])
def list_industry_symbols(industry_name: str, db: Session = Depends(get_db)):
    result = IndustryQueryService(db).list_symbols_by_industry(industry_name)
    if not result:
        raise HTTPException(404, "Industry not found or has no symbols")
    return result
