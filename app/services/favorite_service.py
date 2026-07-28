from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import StockFavorite, StockIndustryBoard, StockMaster
from app.schemas.symbol import SymbolOut


class FavoriteService:
    def __init__(self, db: Session):
        self.db = db

    def list_favorited_symbols(self) -> set[str]:
        rows = self.db.execute(select(StockFavorite.symbol)).scalars().all()
        return set(rows)

    def is_favorited(self, symbol: str) -> bool:
        return self.db.get(StockFavorite, symbol) is not None

    def list_favorites(self) -> list[SymbolOut]:
        rows = self.db.execute(
            select(StockMaster, StockIndustryBoard.board_name, StockFavorite.created_at)
            .join(StockFavorite, StockMaster.symbol == StockFavorite.symbol)
            .outerjoin(StockIndustryBoard, StockMaster.symbol == StockIndustryBoard.symbol)
            .order_by(StockFavorite.created_at.desc(), StockMaster.symbol)
        ).all()
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
                current_industry=ind_name,
            )
            for stock, ind_name, _created_at in rows
        ]

    def add(self, symbol: str) -> bool:
        """Add symbol to favorites. Returns True if newly added."""
        if self.db.get(StockFavorite, symbol):
            return False
        if not self.db.get(StockMaster, symbol):
            raise ValueError(f"股票不存在: {symbol}")
        self.db.add(StockFavorite(symbol=symbol))
        self.db.commit()
        return True

    def remove(self, symbol: str) -> bool:
        """Remove symbol from favorites. Returns True if removed."""
        fav = self.db.get(StockFavorite, symbol)
        if not fav:
            return False
        self.db.delete(fav)
        self.db.commit()
        return True

    def toggle(self, symbol: str) -> bool:
        """Toggle favorite. Returns True if now favorited, False if removed."""
        if self.is_favorited(symbol):
            self.remove(symbol)
            return False
        self.add(symbol)
        return True
