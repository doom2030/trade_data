from datetime import datetime, timedelta, timezone

import pytest

from app.models import CollectJob, CollectJobItem
from collector.retry_service import (
    apply_retry_outcome,
    can_manual_retry_item,
    is_original_failed_item_clause,
    is_retry_child_item,
    retry_failed_job,
)


def _item(status: str, attempt: int = 0, params: dict | None = None) -> CollectJobItem:
    return CollectJobItem(
        job_id=1,
        status=status,
        attempt_count=attempt,
        params=params,
    )


class TestRetryChildFilter:
    def test_retry_child_detected(self):
        item = _item("failed", params={"retry_of_item_id": 99})
        assert is_retry_child_item(item) is True

    def test_original_failed_item_clause_excludes_retry_children(self):
        from sqlalchemy.dialects import postgresql

        compiled = str(
            is_original_failed_item_clause().compile(dialect=postgresql.dialect())
        ).lower()
        assert "params" in compiled
        assert "is null" in compiled

    def test_original_failed_not_child(self):
        item = _item("failed", params=None)
        assert is_retry_child_item(item) is False


class TestManualRetryEligibility:
    def test_failed_allowed(self):
        assert can_manual_retry_item(_item("failed")) is True

    def test_exhausted_allowed(self):
        assert can_manual_retry_item(_item("exhausted")) is True

    def test_success_blocked(self):
        assert can_manual_retry_item(_item("success")) is False

    def test_stale_running_allowed(self):
        item = _item("running")
        item.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
        assert can_manual_retry_item(item, stale_minutes=60) is True

    def test_recent_running_blocked(self):
        item = _item("running")
        item.started_at = datetime.now(timezone.utc)
        assert can_manual_retry_item(item, stale_minutes=60) is False


class TestApplyRetryOutcome:
    def test_success_marks_compensated(self):
        src = _item("failed", attempt=2)
        new = _item("success")
        apply_retry_outcome(None, new, src, max_attempts=3)
        assert src.status == "compensated"

    def test_failure_marks_exhausted_at_limit(self):
        src = _item("failed", attempt=3)
        new = _item("failed")
        apply_retry_outcome(None, new, src, max_attempts=3)
        assert src.status == "exhausted"

    def test_failure_stays_failed_below_limit(self):
        src = _item("failed", attempt=1)
        new = _item("failed")
        apply_retry_outcome(None, new, src, max_attempts=3)
        assert src.status == "failed"


class _FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values

    def first(self):
        return self.values[0] if self.values else None


class _FakeSession:
    def __init__(self, job, items):
        self.job = job
        self.items = items
        self.added_jobs = []
        self.committed = False

    def get(self, model, key):
        if model is CollectJob and key == self.job.id:
            return self.job
        return None

    def scalars(self, query):
        q = str(query).lower()
        if "collect_job_item" in q:
            items = self.items
            if "failed" in q and "exhausted" in q:
                items = [i for i in items if i.status in ("failed", "exhausted")]
            return _FakeScalars(items)
        return _FakeScalars([])

    def add(self, obj):
        if isinstance(obj, CollectJob):
            self.added_jobs.append(obj)

    def flush(self):
        return None

    def commit(self):
        self.committed = True


class TestRetryFailedJob:
    def test_raises_when_no_retryable_items(self, monkeypatch):
        job = CollectJob(id=1, job_type="daily_update", status="failed")
        items = [
            CollectJobItem(id=11, job_id=1, status="failed", params={"retry_of_item_id": 9}),
        ]
        session = _FakeSession(job, items)

        def fake_create_job(*args, **kwargs):
            raise AssertionError("should not create job when no retryable items")

        monkeypatch.setattr("collector.retry_service.create_job", fake_create_job)

        with pytest.raises(ValueError, match="No retryable items"):
            retry_failed_job(session, 1)
