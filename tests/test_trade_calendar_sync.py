from datetime import date, timedelta

import pytest

from app.models import CollectJob, CollectJobLog, TradeCalendar
from collector.trade_calendar_sync import ensure_trade_calendar_for_date, sync_trade_calendar
from scripts.sync_trade_calendar import default_calendar_range, resolve_calendar_range


class TestSyncTradeCalendarScript:
    def test_default_range_extends_to_next_year_end(self):
        start, end = default_calendar_range(today=date(2026, 7, 15))

        assert start == date(2023, 1, 1)
        assert end == date(2027, 12, 31)

    def test_resolve_range_rejects_reversed_dates(self):
        with pytest.raises(Exception, match="end-date must be >= start-date"):
            resolve_calendar_range("2026-07-15", "2026-07-01")


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


class TestSyncTradeCalendar:
    def test_job_rows_preserved_for_no_item_job(self):
        class FakeResult:
            def all(self):
                return []

        class FakeSession:
            def __init__(self):
                self.job = None
                self.logs = []

            def add(self, obj):
                if isinstance(obj, CollectJob):
                    self.job = obj
                elif isinstance(obj, CollectJobLog):
                    self.logs.append(obj)

            def flush(self):
                if self.job and self.job.id is None:
                    self.job.id = 1

            def commit(self):
                pass

            def execute(self, _stmt):
                pass

            def scalars(self, _query):
                return FakeResult()

        class FakeClient:
            def query_trade_calendar(self, _start, _end):
                return [
                    {"trade_date": date(2026, 7, 1), "is_trading_day": True},
                    {"trade_date": date(2026, 7, 2), "is_trading_day": True},
                ]

        session = FakeSession()
        count = sync_trade_calendar(session, FakeClient(), date(2026, 7, 1), date(2026, 7, 2))

        assert count == 2
        assert session.job.inserted_rows == 2
        assert session.job.status == "success"
