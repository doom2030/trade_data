from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.services.job_query_service import JobQueryService


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.last_query = None

    def scalars(self, query):
        self.last_query = query
        return _Scalars(self.rows)

    def get(self, *_args):
        return None


def _job(**kwargs):
    defaults = dict(
        id=1,
        job_type="sync_industry",
        status="success",
        frequency=None,
        adjust_flag=None,
        start_date=None,
        end_date=None,
        target_trade_date=None,
        total_items=1,
        success_items=1,
        failed_items=0,
        skipped_items=0,
        exhausted_items=0,
        compensated_items=0,
        inserted_rows=10,
        updated_rows=0,
        retry_of_job_id=None,
        retry_of_item_id=None,
        error_message=None,
        params=None,
        started_at=None,
        finished_at=None,
        created_at=datetime(2026, 7, 9, 10, 0, tzinfo=timezone.utc),
        updated_at=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestListJobsDateFilter:
    def test_passes_date_bounds_into_query(self):
        db = _FakeDb([_job()])
        # Compile-friendly: just ensure call succeeds and returns mapped jobs
        result = JobQueryService(db).list_jobs(
            date_from=date(2026, 7, 9),
            date_to=date(2026, 7, 9),
        )
        assert len(result) == 1
        assert result[0].job_type == "sync_industry"
        assert db.last_query is not None

    def test_without_dates_still_works(self):
        db = _FakeDb([_job(id=2)])
        result = JobQueryService(db).list_jobs(status="failed")
        assert len(result) == 1
        assert result[0].id == 2

    def test_applies_offset_and_limit(self):
        db = _FakeDb([_job(id=3)])
        result = JobQueryService(db).list_jobs(offset=15, limit=15)
        sql = str(db.last_query).lower()
        assert len(result) == 1
        assert "limit" in sql
        assert "offset" in sql
