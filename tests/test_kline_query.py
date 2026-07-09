from datetime import date

import pytest
from fastapi import HTTPException

from app.services.kline_query_service import KlineQueryService


class FakeDb:
    pass


class TestKlineDateValidation:
    def test_rejects_reverse_range(self):
        service = KlineQueryService(FakeDb())
        with pytest.raises(HTTPException) as exc:
            service.query_klines("day", "sh.600000", date(2026, 7, 10), date(2026, 7, 1), "forward")
        assert exc.value.status_code == 400
        assert "end must be >= start" in exc.value.detail
