import pytest
from fastapi import HTTPException

from app.services.job_command_service import JobCommandService


class _FakeScalars:
    def first(self):
        return None


class _FakeDb:
    def scalars(self, query):
        return _FakeScalars()


class TestJobCommandServiceRetry:
    def test_retry_job_not_found_raises_404(self, monkeypatch):
        def fake_retry_failed_job(session, job_id, only_failed, max_attempts):
            raise ValueError(f"Job {job_id} not found")

        monkeypatch.setattr(
            "app.services.job_command_service.retry_failed_job",
            fake_retry_failed_job,
        )

        service = JobCommandService(db=_FakeDb())
        with pytest.raises(HTTPException) as exc:
            service.retry_job(999)
        assert exc.value.status_code == 404

    def test_retry_job_invalid_raises_400(self, monkeypatch):
        def fake_retry_failed_job(session, job_id, only_failed, max_attempts):
            raise ValueError("No retryable items found for this job")

        monkeypatch.setattr(
            "app.services.job_command_service.retry_failed_job",
            fake_retry_failed_job,
        )

        service = JobCommandService(db=_FakeDb())
        with pytest.raises(HTTPException) as exc:
            service.retry_job(1)
        assert exc.value.status_code == 400


class TestJobCommandServiceTrimScope:
    def test_rejects_weekly_monthly_actions(self):
        service = JobCommandService(db=_FakeDb())
        with pytest.raises(HTTPException) as exc:
            service.trigger_job("update_weekly", {"end_date": "2026-07-01"})
        assert exc.value.status_code == 400
        assert "unsupported" in str(exc.value.detail).lower()

        with pytest.raises(HTTPException) as exc:
            service.trigger_job("update_monthly", {"end_date": "2026-07-01"})
        assert exc.value.status_code == 400
