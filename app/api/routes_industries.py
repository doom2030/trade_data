from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.symbol import IndustryOut, IndustrySymbolOut
from app.services.industry_query_service import IndustryQueryService

router = APIRouter(prefix="/api/industries", tags=["industries"])


@router.get("", response_model=list[IndustryOut])
def list_industries(db: Session = Depends(get_db)):
    return IndustryQueryService(db).list_industries()


@router.get("/{industry_name}/symbols", response_model=list[IndustrySymbolOut])
def list_industry_symbols(industry_name: str, db: Session = Depends(get_db)):
    result = IndustryQueryService(db).list_symbols_by_industry(industry_name)
    if not result:
        raise HTTPException(404, "Industry not found or has no symbols")
    return result
