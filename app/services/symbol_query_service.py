from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.templates import BOARD_LABELS
from app.models import StockIndustryBoard, StockMaster
from app.schemas.symbol import SymbolOut

BOARD_ORDER = ("sh_main", "sz_main", "chinext", "star")


class SymbolQueryService:
    def __init__(self, db: Session):
        self.db = db

    def query_symbols(
        self,
        board: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        include_excluded: bool = False,
        industry: str | None = None,
    ) -> list[SymbolOut]:
        query = select(StockMaster, StockIndustryBoard.board_name).outerjoin(
            StockIndustryBoard, StockMaster.symbol == StockIndustryBoard.symbol
        )
        query = self._apply_filters(query, board, status, keyword, include_excluded, industry)
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
                current_industry=ind_name,
            )
            for stock, ind_name in rows
        ]

    def count_by_board(
        self,
        status: str | None = None,
        keyword: str | None = None,
        include_excluded: bool = False,
        industry: str | None = None,
    ) -> dict[str, int]:
        """Return stock counts per board code (plus '' for all)."""
        query = (
            select(StockMaster.board, func.count())
            .select_from(StockMaster)
            .outerjoin(StockIndustryBoard, StockMaster.symbol == StockIndustryBoard.symbol)
        )
        query = self._apply_filters(
            query, board=None, status=status, keyword=keyword,
            include_excluded=include_excluded, industry=industry,
        )
        query = query.group_by(StockMaster.board)
        rows = self.db.execute(query).all()
        by_board = {code: count for code, count in rows}
        return {
            "": sum(by_board.values()),
            **{code: by_board.get(code, 0) for code in BOARD_ORDER},
        }

    def list_industries(
        self,
        board: str | None = None,
        status: str | None = None,
        include_excluded: bool = False,
    ) -> list[str]:
        """Industry names available under the current board/status filters."""
        query = (
            select(StockIndustryBoard.board_name, func.count())
            .select_from(StockMaster)
            .join(StockIndustryBoard, StockMaster.symbol == StockIndustryBoard.symbol)
        )
        query = self._apply_status(query, status, include_excluded)
        if board:
            query = query.where(StockMaster.board == board)
        query = (
            query.where(StockIndustryBoard.board_name.is_not(None))
            .group_by(StockIndustryBoard.board_name)
            .order_by(StockIndustryBoard.board_name)
        )
        return [name for name, _count in self.db.execute(query).all()]

    @staticmethod
    def board_tabs() -> list[dict[str, str]]:
        return [{"code": "", "label": "全部"}, *[
            {"code": code, "label": BOARD_LABELS[code]} for code in BOARD_ORDER
        ]]

    def _apply_filters(self, query, board, status, keyword, include_excluded, industry):
        query = self._apply_status(query, status, include_excluded)
        if board:
            query = query.where(StockMaster.board == board)
        if industry:
            query = query.where(StockIndustryBoard.board_name == industry)
        if keyword:
            query = query.where(
                or_(
                    StockMaster.name.contains(keyword),
                    StockMaster.code.contains(keyword),
                    StockMaster.symbol.contains(keyword),
                )
            )
        return query

    @staticmethod
    def _apply_status(query, status: str | None, include_excluded: bool):
        if include_excluded:
            if status:
                return query.where(StockMaster.status == status)
            return query
        return query.where(StockMaster.status == "active")
