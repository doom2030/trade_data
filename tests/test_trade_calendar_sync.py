from datetime import date, timedelta

from app.models import TradeCalendar
from collector.trade_calendar_sync import ensure_trade_calendar_for_date


class TestEnsureTradeCalendarForDate:
    def test_skips_sync_when_calendar_exists(self, monkeypatch):
        target = date(2026, 7, 8)
        cal = TradeCalendar(trade_date=target, is_trading_day=True)

        class FakeSession:
            def get(self, model, key):
                if model is TradeCalendar and key == target:
                    return cal
                return None

        def fake_sync(*args, **kwargs):
            raise AssertionError("sync should not run when calendar exists")

        monkeypatch.setattr("collector.trade_calendar_sync.sync_trade_calendar", fake_sync)
        assert ensure_trade_calendar_for_date(FakeSession(), None, target) is True

    def test_syncs_when_calendar_missing(self, monkeypatch):
        target = date(2026, 7, 8)

        class FakeSession:
            def __init__(self):
                self.calendar: dict[date, TradeCalendar] = {}

            def get(self, model, key):
                if model is TradeCalendar:
                    return self.calendar.get(key)
                return None

        session = FakeSession()
        synced_ranges: list[tuple[date, date]] = []

        def fake_sync(_session, _client, start_date, end_date):
            synced_ranges.append((start_date, end_date))
            session.calendar[target] = TradeCalendar(trade_date=target, is_trading_day=True)

        monkeypatch.setattr("collector.trade_calendar_sync.sync_trade_calendar", fake_sync)
        assert ensure_trade_calendar_for_date(session, None, target, window_days=7) is True
        assert synced_ranges == [(target - timedelta(days=7), target + timedelta(days=7))]
