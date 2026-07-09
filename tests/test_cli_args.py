import pytest

from collector.cli_args import resolve_adjust_flags, resolve_frequencies


class TestCliArgs:
    def test_resolve_frequency_single(self):
        assert resolve_frequencies("day") == ["day"]

    def test_resolve_frequency_all(self):
        freqs = resolve_frequencies("all", allow_all=True)
        assert "day" in freqs

    def test_invalid_frequency(self):
        with pytest.raises(ValueError, match="Invalid frequency"):
            resolve_frequencies("hourly")

    def test_resolve_adjust_single(self):
        assert resolve_adjust_flags("forward") == ["forward"]

    def test_invalid_adjust(self):
        with pytest.raises(ValueError, match="Invalid adjust flag"):
            resolve_adjust_flags("magic")
