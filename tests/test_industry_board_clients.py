import json

import pytest

from collector.industry_board_clients import (
    IndustryBoardFetchError,
    fetch_sw_constituents,
    fetch_ths_constituents,
)


class TestFetchThsConstituents:
    def test_parses_quotebridge_payload(self, monkeypatch):
        payload = {
            "block": {"name": "半导体", "subcodeCount": 2},
            "items": [
                {"5": "688981", "55": "中芯国际"},
                {"5": "300750", "55": "宁德时代"},
                {"5": "830799", "55": "北交所应跳过"},
            ],
        }
        body = f"quotebridge_v2_blockrank_881121_199112_d500({json.dumps(payload)})"

        class FakeResp:
            text = body
            status_code = 200

            def raise_for_status(self):
                return None

        monkeypatch.setattr(
            "collector.industry_board_clients.requests.get",
            lambda *args, **kwargs: FakeResp(),
        )
        symbols = fetch_ths_constituents("881121")
        assert symbols == ["sh.688981", "sz.300750"]

    def test_invalid_payload_raises(self, monkeypatch):
        class FakeResp:
            text = "not-jsonp"
            status_code = 200

            def raise_for_status(self):
                return None

        monkeypatch.setattr(
            "collector.industry_board_clients.requests.get",
            lambda *args, **kwargs: FakeResp(),
        )
        with pytest.raises(IndustryBoardFetchError):
            fetch_ths_constituents("881121")


class TestFetchSwConstituents:
    def test_normalizes_codes(self, monkeypatch):
        import pandas as pd

        df = pd.DataFrame(
            {
                "证券代码": ["600519", "000001", "830799"],
                "证券名称": ["贵州茅台", "平安银行", "北交所"],
            }
        )
        monkeypatch.setattr(
            "collector.industry_board_clients.ak.index_component_sw",
            lambda code: df,
        )
        symbols = fetch_sw_constituents("801016.SI")
        assert symbols == ["sh.600519", "sz.000001"]
