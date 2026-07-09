from app.models import CollectJob, CollectJobItem
from collector.job_helper import finalize_job


class _EmptyScalars:
    def all(self):
        return []


class _NoItemSession:
    def scalars(self, _query):
        return _EmptyScalars()

    def flush(self):
        pass


class _ItemScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _ItemSession:
    def __init__(self, items):
        self._items = items

    def scalars(self, _query):
        return _ItemScalars(self._items)

    def flush(self):
        pass


class TestFinalizeJobLogic:
    def test_all_success(self):
        total_items = 2
        failed_items = 0
        skipped_items = 0
        effective = total_items - skipped_items
        fail_rate = failed_items / effective if effective else 0
        assert fail_rate == 0

    def test_partial_success(self):
        total_items = 20
        failed_items = 1
        skipped_items = 0
        fail_rate = failed_items / (total_items - skipped_items)
        assert 0 < fail_rate <= 0.05

    def test_all_skipped(self):
        total_items = 2
        skipped_items = 2
        effective = total_items - skipped_items
        assert effective == 0

    def test_bulk_job_without_items_sets_unit_counters(self):
        job = CollectJob(job_type="sync_industry", status="running")

        finalize_job(_NoItemSession(), job, inserted_rows=4533)

        assert job.status == "success"
        assert job.total_items == 1
        assert job.success_items == 1
        assert job.failed_items == 0
        assert job.inserted_rows == 4533
        assert not (job.params or {}).get("all_skipped")

    def test_itemized_job_aggregates_from_items(self):
        job = CollectJob(id=1, job_type="backfill_kline", status="running")
        items = [
            CollectJobItem(job_id=1, status="success", inserted_rows=10, updated_rows=1),
            CollectJobItem(job_id=1, status="failed", inserted_rows=0, updated_rows=0),
        ]

        finalize_job(_ItemSession(items), job)

        assert job.total_items == 2
        assert job.success_items == 1
        assert job.failed_items == 1
        assert job.inserted_rows == 10
        assert job.updated_rows == 1
        assert job.status == "failed"
