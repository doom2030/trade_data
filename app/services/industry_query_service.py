from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import IndustryBoard, StockIndustryBoard, StockMaster
from app.schemas.symbol import IndustryOut, IndustrySymbolOut
from collector.industry_board_utils import LETTER_BUCKETS, letter_bucket


class IndustryQueryService:
    def __init__(self, db: Session):
        self.db = db

    def list_industries(self) -> list[IndustryOut]:
        count_subq = (
            select(
                StockIndustryBoard.board_code,
                func.count(StockIndustryBoard.symbol).label("symbol_count"),
            )
            .group_by(StockIndustryBoard.board_code)
            .subquery()
        )
        rows = self.db.execute(
            select(
                IndustryBoard.board_code,
                IndustryBoard.board_name,
                IndustryBoard.pinyin_initial,
                func.coalesce(count_subq.c.symbol_count, 0),
            )
            .outerjoin(count_subq, IndustryBoard.board_code == count_subq.c.board_code)
            .order_by(IndustryBoard.pinyin_initial, IndustryBoard.board_name)
        ).all()
        return [
            IndustryOut(
                industry_name=name,
                symbol_count=int(count),
                board_code=code,
                pinyin_initial=initial,
            )
            for code, name, initial, count in rows
            if name
        ]

    def list_industries_grouped(self) -> dict[str, list[IndustryOut]]:
        grouped: dict[str, list[IndustryOut]] = {bucket: [] for bucket in LETTER_BUCKETS}
        for industry in self.list_industries():
            bucket = letter_bucket(industry.pinyin_initial or "#")
            grouped.setdefault(bucket, []).append(industry)
        return grouped

    def list_symbols_by_industry(self, industry_name: str) -> list[IndustrySymbolOut]:
        rows = self.db.execute(
            select(StockMaster)
            .join(StockIndustryBoard, StockMaster.symbol == StockIndustryBoard.symbol)
            .where(StockIndustryBoard.board_name == industry_name)
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
