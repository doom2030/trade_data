from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from collector.scheduler import is_schedule_due, parse_weekdays


class TestSchedulerHelpers:
    def test_parse_weekdays(self):
        assert parse_weekdays("0,1,2,3,4") == {0, 1, 2, 3, 4}
        assert parse_weekdays("4") == {4}

    def test_parse_weekdays_rejects_invalid(self):
        with pytest.raises(ValueError):
            parse_weekdays("7")

    def test_is_due_before_time(self):
        now = datetime(2026, 7, 24, 19, 59, tzinfo=ZoneInfo("Asia/Shanghai"))  # Friday
        assert (
            is_schedule_due(
                now,
                hour=20,
                minute=0,
                weekdays={0, 1, 2, 3, 4},
                already_ran_on=None,
            )
            is False
        )

    def test_is_due_at_time(self):
        now = datetime(2026, 7, 24, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai"))  # Friday
        assert (
            is_schedule_due(
                now,
                hour=20,
                minute=0,
                weekdays={0, 1, 2, 3, 4},
                already_ran_on=None,
            )
            is True
        )

    def test_is_due_skips_weekend(self):
        now = datetime(2026, 7, 25, 20, 30, tzinfo=ZoneInfo("Asia/Shanghai"))  # Saturday
        assert (
            is_schedule_due(
                now,
                hour=20,
                minute=0,
                weekdays={0, 1, 2, 3, 4},
                already_ran_on=None,
            )
            is False
        )

    def test_is_due_skips_same_day_rerun(self):
        now = datetime(2026, 7, 24, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert (
            is_schedule_due(
                now,
                hour=20,
                minute=0,
                weekdays={0, 1, 2, 3, 4},
                already_ran_on=now.date(),
            )
            is False
        )
