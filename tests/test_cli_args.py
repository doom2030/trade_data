import pytest

from app.core.config import get_settings
from collector.cli_args import resolve_adjust_flags, resolve_frequencies


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestCliArgs:
    def test_resolve_frequency_single(self):
        assert resolve_frequencies("day") == ["day"]

    def test_resolve_frequency_all(self):
        freqs = resolve_frequencies("all", allow_all=True)
        assert freqs == ["day"]

    def test_invalid_frequency(self):
        with pytest.raises(ValueError, match="Invalid frequency"):
            resolve_frequencies("hourly")
        with pytest.raises(ValueError, match="Invalid frequency"):
            resolve_frequencies("week")
        with pytest.raises(ValueError, match="Invalid frequency"):
            resolve_frequencies("month")

    def test_resolve_adjust_single(self):
        assert resolve_adjust_flags("forward") == ["forward"]

    def test_resolve_adjust_all(self):
        assert resolve_adjust_flags("all", allow_all=True) == ["forward"]

    def test_invalid_adjust(self):
        with pytest.raises(ValueError, match="Invalid adjust flag"):
            resolve_adjust_flags("magic")
        with pytest.raises(ValueError, match="Invalid adjust flag"):
            resolve_adjust_flags("none")
        with pytest.raises(ValueError, match="Invalid adjust flag"):
            resolve_adjust_flags("backward")
