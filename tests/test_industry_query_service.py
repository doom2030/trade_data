from app.schemas.symbol import IndustryOut
from app.services.industry_query_service import IndustryQueryService
from collector.industry_board_utils import LETTER_BUCKETS


class TestListIndustriesGrouped:
    def test_groups_by_letter_bucket(self, monkeypatch):
        industries = [
            IndustryOut(industry_name="半导体", symbol_count=10, board_code="BK1", pinyin_initial="B"),
            IndustryOut(industry_name="银行", symbol_count=20, board_code="BK2", pinyin_initial="Y"),
            IndustryOut(industry_name="房地产", symbol_count=5, board_code="BK3", pinyin_initial="F"),
        ]

        monkeypatch.setattr(
            IndustryQueryService,
            "list_industries",
            lambda self: industries,
        )
        grouped = IndustryQueryService(db=None).list_industries_grouped()
        assert set(grouped.keys()) == set(LETTER_BUCKETS)
        assert [i.industry_name for i in grouped["A~E"]] == ["半导体"]
        assert [i.industry_name for i in grouped["F~J"]] == ["房地产"]
        assert [i.industry_name for i in grouped["U~Z"]] == ["银行"]
        assert grouped["K~O"] == []
        assert grouped["P~T"] == []
