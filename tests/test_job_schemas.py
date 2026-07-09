import pytest
from pydantic import ValidationError

from app.schemas.job import JobItemRetryRequest, JobRetryRequest


class TestJobRetrySchemas:
    def test_default_max_attempts(self):
        assert JobRetryRequest().max_attempts == 3
        assert JobItemRetryRequest().max_attempts == 3

    def test_max_attempts_within_bounds(self):
        assert JobRetryRequest(max_attempts=15).max_attempts == 15
        assert JobItemRetryRequest(max_attempts=1).max_attempts == 1

    def test_max_attempts_rejects_zero(self):
        with pytest.raises(ValidationError):
            JobRetryRequest(max_attempts=0)

    def test_max_attempts_rejects_negative(self):
        with pytest.raises(ValidationError):
            JobItemRetryRequest(max_attempts=-1)

    def test_max_attempts_rejects_too_large(self):
        with pytest.raises(ValidationError):
            JobRetryRequest(max_attempts=16)
