from datetime import date

import pytest

from app.models import CollectJobItem, TradeCalendar
from collector.kline_sync import analyze_suspension_from_items, is_trading_day


class FakeSession:
    def __init__(self, calendar: TradeCalendar | None):
        self._calendar = calendar

    def get(self, model, key):
        if model is TradeCalendar:
            return self._calendar
        return None


def _item(
    adjust: str,
    status: str,
    rows: int = 0,
    error: str | None = None,
    params: dict | None = None,
) -> CollectJobItem:
    item = CollectJobItem(
        job_id=1,
        symbol="sh.600000",
        frequency="day",
        adjust_flag=adjust,
        start_date=date(2026, 7, 8),
        end_date=date(2026, 7, 8),
        status=status,
        inserted_rows=rows,
        updated_rows=0,
        error_message=error,
        params=params,
    )
    return item


class TestIsTradingDay:
    def test_trading_day(self):
        session = FakeSession(TradeCalendar(trade_date=date(2026, 7, 8), is_trading_day=True))
        assert is_trading_day(session, date(2026, 7, 8)) is True

    def test_non_trading_day(self):
        session = FakeSession(TradeCalendar(trade_date=date(2026, 7, 5), is_trading_day=False))
        assert is_trading_day(session, date(2026, 7, 5)) is False

    def test_missing_calendar_entry(self):
        session = FakeSession(None)
        assert is_trading_day(session, date(2026, 7, 1)) is False


class TestAnalyzeSuspensionFromItems:
    def test_infer_suspended_when_all_empty(self):
        items = {
            "none": _item("none", "success", 0),
            "forward": _item("forward", "success", 0),
            "backward": _item("backward", "success", 0),
        }
        outcome, counts, errors = analyze_suspension_from_items(items, ["none", "forward", "backward"])
        assert outcome == "suspended"
        assert all(v == 0 for v in counts.values())
        assert errors == {}

    def test_has_data_resolves(self):
        items = {
            "none": _item("none", "success", 1),
            "forward": _item("forward", "success", 0),
            "backward": _item("backward", "success", 0),
        }
        outcome, _, _ = analyze_suspension_from_items(items, ["none", "forward", "backward"])
        assert outcome == "has_data"

    def test_failed_adjust_blocks_inference(self):
        items = {
            "none": _item("none", "success", 0),
            "forward": _item("forward", "failed", 0, error="network"),
            "backward": _item("backward", "success", 0),
        }
        outcome, _, errors = analyze_suspension_from_items(items, ["none", "forward", "backward"])
        assert outcome is None
        assert "forward" in errors

    def test_skipped_item_blocks_inference(self):
        items = {
            "none": _item("none", "skipped", 0),
            "forward": _item("forward", "success", 0),
            "backward": _item("backward", "success", 0),
        }
        outcome, _, _ = analyze_suspension_from_items(items, ["none", "forward", "backward"])
        assert outcome is None

    def test_st_filtered_all_blocks_suspension_inference(self):
        items = {
            "none": _item("none", "success", 0, params={"st_filtered_all": True}),
            "forward": _item("forward", "success", 0, params={"st_filtered_all": True}),
            "backward": _item("backward", "success", 0, params={"st_filtered_all": True}),
        }
        outcome, _, _ = analyze_suspension_from_items(items, ["none", "forward", "backward"])
        assert outcome is None


class TestCatchupJobParams:
    def test_trade_dates_from_params(self):
        from app.models import CollectJob
        from collector.kline_sync import _catchup_trade_dates

        job = CollectJob(
            job_type="catchup_daily_update",
            status="pending",
            params={"trade_dates": ["2026-07-01", "2026-07-02"]},
        )
        dates = _catchup_trade_dates(job)
        assert dates == [date(2026, 7, 1), date(2026, 7, 2)]

    def test_create_catchup_jobs_creates_single_job_for_all_dates(self, monkeypatch):
        from collector.kline_sync import create_catchup_jobs

        created = []

        class FakeSession:
            def commit(self):
                pass

            def add(self, obj):
                created.append(obj)

            def flush(self):
                created[-1].id = len(created)

        ids = create_catchup_jobs(
            FakeSession(),
            [date(2026, 7, 3), date(2026, 7, 1), date(2026, 7, 2)],
        )

        assert ids == [1]
        assert len(created) == 1
        assert created[0].start_date == date(2026, 7, 1)
        assert created[0].end_date == date(2026, 7, 3)
        assert created[0].params == {"trade_dates": ["2026-07-01", "2026-07-02", "2026-07-03"]}


class TestGetMissedTradingDays:
    def test_finds_middle_gap_after_later_success(self):
        from app.models import CollectJob
        from collector.kline_sync import get_missed_trading_days

        d1, d2, d3 = date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)
        calendars = [d1, d2, d3]
        jobs = [
            CollectJob(
                job_type="daily_update",
                status="failed",
                target_trade_date=d2,
            ),
            CollectJob(
                job_type="daily_update",
                status="success",
                target_trade_date=d3,
            ),
        ]

        class FakeSession:
            def __init__(self):
                self.collect_job_calls = 0

            def scalars(self, query):
                class Result:
                    def __init__(self, values):
                        self.values = values

                    def all(self):
                        return self.values

                q = str(query).lower()
                if "trade_calendar" in q:
                    return Result(calendars)
                if "collect_job" in q:
                    self.collect_job_calls += 1
                    if self.collect_job_calls == 1:
                        successful = [j for j in jobs if j.status in ("success", "partial_success")]
                        return Result(successful)
                    return Result([])
                return Result([])

        missed = get_missed_trading_days(FakeSession(), d3)
        assert missed == [d1, d2]

    def test_catchup_job_covers_multiple_days(self):
        from app.models import CollectJob
        from collector.kline_sync import get_missed_trading_days

        d1, d2, d3 = date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)
        calendars = [d1, d2, d3]
        jobs = [
            CollectJob(
                job_type="catchup_daily_update",
                status="success",
                start_date=d1,
                end_date=d2,
                target_trade_date=d2,
                params={"trade_dates": [d1.isoformat(), d2.isoformat()]},
            ),
            CollectJob(
                job_type="daily_update",
                status="success",
                target_trade_date=d3,
            ),
        ]

        class FakeSession:
            def __init__(self):
                self.collect_job_calls = 0

            def scalars(self, query):
                class Result:
                    def __init__(self, values):
                        self.values = values

                    def all(self):
                        return self.values

                q = str(query).lower()
                if "trade_calendar" in q:
                    return Result(calendars)
                if "collect_job" in q:
                    self.collect_job_calls += 1
                    if self.collect_job_calls == 1:
                        successful = [j for j in jobs if j.status in ("success", "partial_success")]
                        return Result(successful)
                    return Result([])
                return Result([])

        missed = get_missed_trading_days(FakeSession(), d3)
        assert missed == []

    def test_pending_catchup_blocks_duplicate_creation(self):
        from app.models import CollectJob
        from collector.kline_sync import get_missed_trading_days

        d1, d2 = date(2026, 7, 1), date(2026, 7, 2)
        calendars = [d1, d2]
        completed_jobs: list[CollectJob] = []
        inflight_jobs = [
            CollectJob(
                job_type="catchup_daily_update",
                status="pending",
                start_date=d1,
                end_date=d2,
                target_trade_date=d2,
                params={"trade_dates": [d1.isoformat(), d2.isoformat()]},
            ),
        ]

        class FakeSession:
            def __init__(self):
                self.collect_job_calls = 0

            def scalars(self, query):
                class Result:
                    def __init__(self, values):
                        self.values = values

                    def all(self):
                        return self.values

                q = str(query).lower()
                if "trade_calendar" in q:
                    return Result(calendars)
                if "collect_job" in q:
                    self.collect_job_calls += 1
                    if self.collect_job_calls == 1:
                        return Result(completed_jobs)
                    return Result(inflight_jobs)
                return Result([])

        missed = get_missed_trading_days(FakeSession(), d2)
        assert missed == []

    def test_failed_catchup_does_not_block_retry(self):
        from app.models import CollectJob
        from collector.kline_sync import get_missed_trading_days

        d1 = date(2026, 7, 1)
        calendars = [d1]
        completed_jobs = [
            CollectJob(
                job_type="catchup_daily_update",
                status="failed",
                start_date=d1,
                end_date=d1,
                target_trade_date=d1,
                params={"trade_dates": [d1.isoformat()]},
            ),
        ]

        class FakeSession:
            def __init__(self):
                self.collect_job_calls = 0

            def scalars(self, query):
                class Result:
                    def __init__(self, values):
                        self.values = values

                    def all(self):
                        return self.values

                q = str(query).lower()
                if "trade_calendar" in q:
                    return Result(calendars)
                if "collect_job" in q:
                    self.collect_job_calls += 1
                    if self.collect_job_calls == 1:
                        return Result(
                            [j for j in completed_jobs if j.status in ("success", "partial_success")]
                        )
                    return Result([])
                return Result([])

        missed = get_missed_trading_days(FakeSession(), d1)
        assert missed == [d1]


class TestMissingKlineRanges:
    def test_day_skips_covered_and_suspended(self):
        from collector.kline_sync import missing_kline_ranges

        trading = [
            date(2026, 7, 1),
            date(2026, 7, 2),
            date(2026, 7, 3),
            date(2026, 7, 4),
        ]
        existing = [date(2026, 7, 1), date(2026, 7, 2)]
        suspended = [date(2026, 7, 3)]

        class FakeSession:
            def scalars(self, query):
                class Result:
                    def __init__(self, values):
                        self.values = values

                    def all(self):
                        return self.values

                q = str(query).lower()
                if "stock_suspension" in q:
                    return Result(suspended)
                if "trade_calendar" in q:
                    return Result(trading)
                # kline_day existing dates
                return Result(existing)

        ranges = missing_kline_ranges(
            FakeSession(),
            symbol="sz.002240",
            frequency="day",
            adjust_flag="forward",
            start=date(2026, 7, 1),
            end=date(2026, 7, 4),
        )
        assert ranges == [(date(2026, 7, 4), date(2026, 7, 4))]

    def test_day_complete_returns_empty(self):
        from collector.kline_sync import missing_kline_ranges

        trading = [date(2026, 7, 1), date(2026, 7, 2)]
        existing = trading[:]

        class FakeSession:
            def scalars(self, query):
                class Result:
                    def __init__(self, values):
                        self.values = values

                    def all(self):
                        return self.values

                q = str(query).lower()
                if "stock_suspension" in q:
                    return Result([])
                if "trade_calendar" in q:
                    return Result(trading)
                return Result(existing)

        ranges = missing_kline_ranges(
            FakeSession(),
            symbol="sh.600000",
            frequency="day",
            adjust_flag="forward",
            start=date(2026, 7, 1),
            end=date(2026, 7, 2),
        )
        assert ranges == []

    def test_rejects_non_day_frequency(self):
        from collector.kline_sync import missing_kline_ranges

        with pytest.raises(ValueError, match="Unsupported frequency"):
            missing_kline_ranges(
                object(),
                symbol="sh.600000",
                frequency="week",
                adjust_flag="forward",
                start=date(2026, 1, 1),
                end=date(2026, 3, 15),
            )


class TestCollectKlineItemSkip:
    def test_day_complete_skips_baostock(self, monkeypatch):
        from app.models import CollectJobItem, StockMaster
        from collector.kline_sync import collect_kline_item

        stock = StockMaster(
            symbol="sh.600000",
            exchange="sh",
            code="600000",
            name="浦发银行",
            board="sh_main",
            status="active",
        )
        item = CollectJobItem(
            id=1,
            job_id=10,
            symbol="sh.600000",
            frequency="day",
            adjust_flag="forward",
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 2),
            status="pending",
        )

        class Session:
            def __init__(self):
                self.committed = False

            def get(self, model, key):
                if model is StockMaster:
                    return stock
                return None

            def flush(self):
                return None

            def commit(self):
                self.committed = True

        class Client:
            def __init__(self):
                self.called = False

            def query_kline(self, *args, **kwargs):
                self.called = True
                raise AssertionError("baostock should not be called")

        monkeypatch.setattr(
            "collector.kline_sync.missing_kline_ranges",
            lambda *args, **kwargs: [],
        )

        session = Session()
        client = Client()
        collect_kline_item(session, client, item)

        assert item.status == "skipped"
        assert item.error_message == "Already complete in range"
        assert item.finished_at is not None
        assert session.committed is True
        assert client.called is False
