from datetime import date
from types import SimpleNamespace

from app.services.symbol_query_service import BOARD_ORDER, SymbolQueryService


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.last_query = None

    def execute(self, query):
        self.last_query = query
        return _Result(self.rows)


def _stock(symbol, board="sh_main", status="active", name=None):
    code = symbol.split(".")[-1]
    return SimpleNamespace(
        symbol=symbol,
        exchange=symbol.split(".")[0],
        code=code,
        name=name or symbol,
        board=board,
        ipo_date=date(2020, 1, 1),
        out_date=None,
        status=status,
    )


class TestSymbolQueryService:
    def test_board_tabs_order(self):
        tabs = SymbolQueryService.board_tabs()
        assert tabs[0] == {"code": "", "label": "全部"}
        assert [t["code"] for t in tabs[1:]] == list(BOARD_ORDER)

    def test_query_symbols_maps_industry(self):
        stock = _stock("sh.600000", name="浦发银行")
        db = _FakeDb([(stock, "银行")])
        result = SymbolQueryService(db).query_symbols()
        assert len(result) == 1
        assert result[0].symbol == "sh.600000"
        assert result[0].current_industry == "银行"

    def test_count_by_board_includes_all_key(self):
        db = _FakeDb([("sh_main", 10), ("star", 3)])
        counts = SymbolQueryService(db).count_by_board()
        assert counts[""] == 13
        assert counts["sh_main"] == 10
        assert counts["sz_main"] == 0
        assert counts["star"] == 3

    def test_list_industries_returns_names(self):
        db = _FakeDb([("半导体", 12), ("白酒", 5)])
        names = SymbolQueryService(db).list_industries(board="star")
        assert names == ["半导体", "白酒"]
