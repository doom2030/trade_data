from datetime import date

from collector.stock_meta_sync import _is_delisted


class TestIsDelisted:
    def test_out_date_on_or_before_snapshot(self):
        assert _is_delisted(date(2026, 1, 1), date(2026, 7, 1)) is True

    def test_out_date_after_snapshot(self):
        assert _is_delisted(date(2026, 12, 31), date(2026, 7, 1)) is False

    def test_missing_out_date(self):
        assert _is_delisted(None, date(2026, 7, 1)) is False
