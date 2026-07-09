from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import StockIndustryCurrent, StockMaster
from app.schemas.symbol import SymbolOut


def _to_float(val: Decimal | None) -> float | None:
    return float(val) if val is not None else None


class SymbolQueryService:
    def __init__(self, db: Session):
        self.db = db

    def query_symbols(
        self,
        board: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        include_excluded: bool = False,
    ) -> list[SymbolOut]:
        query = select(StockMaster, StockIndustryCurrent.industry_name).outerjoin(
            StockIndustryCurrent, StockMaster.symbol == StockIndustryCurrent.symbol
        )

        if include_excluded:
            if status:
                query = query.where(StockMaster.status == status)
        else:
            query = query.where(StockMaster.status == "active")

        if board:
            query = query.where(StockMaster.board == board)

        if keyword:
            query = query.where(
                or_(
                    StockMaster.name.contains(keyword),
                    StockMaster.code.contains(keyword),
                    StockMaster.symbol.contains(keyword),
                )
            )

        query = query.order_by(StockMaster.symbol)
        rows = self.db.execute(query).all()

        return [
            SymbolOut(
                symbol=stock.symbol,
                exchange=stock.exchange,
                code=stock.code,
                name=stock.name,
                board=stock.board,
                ipo_date=stock.ipo_date,
                out_date=stock.out_date,
                status=stock.status,
                current_industry=industry,
            )
            for stock, industry in rows
        ]
