from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import StockIndustryCurrent, StockMaster
from app.schemas.symbol import IndustryOut, IndustrySymbolOut


class IndustryQueryService:
    def __init__(self, db: Session):
        self.db = db

    def list_industries(self) -> list[IndustryOut]:
        rows = self.db.execute(
            select(
                StockIndustryCurrent.industry_name,
                func.count(StockIndustryCurrent.symbol),
            )
            .where(StockIndustryCurrent.industry_name.isnot(None))
            .group_by(StockIndustryCurrent.industry_name)
            .order_by(StockIndustryCurrent.industry_name)
        ).all()
        return [
            IndustryOut(industry_name=name, symbol_count=count)
            for name, count in rows
            if name
        ]

    def list_symbols_by_industry(self, industry_name: str) -> list[IndustrySymbolOut]:
        rows = self.db.execute(
            select(StockMaster)
            .join(StockIndustryCurrent, StockMaster.symbol == StockIndustryCurrent.symbol)
            .where(StockIndustryCurrent.industry_name == industry_name)
            .order_by(StockMaster.symbol)
        ).scalars().all()
        return [
            IndustrySymbolOut(
                symbol=s.symbol,
                name=s.name,
                board=s.board,
                status=s.status,
            )
            for s in rows
        ]
