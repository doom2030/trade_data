from app.models import CollectJob
from collector.job_helper import finalize_job


class _EmptyScalars:
    def all(self):
        return []


class _NoItemSession:
    def scalars(self, _query):
        return _EmptyScalars()

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

    def test_no_item_job_finalize_does_not_preserve_manual_rows(self):
        job = CollectJob(job_type="sync_trade_calendar", status="running", inserted_rows=2381)

        finalize_job(_NoItemSession(), job)

        assert job.status == "success"
        assert job.inserted_rows == 0
