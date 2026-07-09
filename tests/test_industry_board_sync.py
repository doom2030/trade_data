from datetime import date

import pytest

from collector.industry_board_clients import IndustryBoardFetchError
from collector.industry_board_sync import _load_boards_and_members, sync_industry_boards


class _FakeScalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _FakeSession:
    def __init__(self, symbols: list[str] | None = None):
        self._symbols = symbols or ["sh.600519", "sz.000001", "sz.300750"]

    def scalars(self, query):
        return _FakeScalars(self._symbols)


class _WipeGuardSession:
    """Minimal session for sync_industry_boards empty-membership guard."""

    def __init__(self, *, active_count: int, existing_count: int):
        self.active_count = active_count
        self.existing_count = existing_count
        self.job = None
        self.deleted = False
        self.committed = False
        self._scalar_calls = 0

    def add(self, obj):
        self.job = obj

    def flush(self):
        if self.job is not None and getattr(self.job, "id", None) is None:
            self.job.id = 1

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def get(self, _cls, _id):
        return self.job

    def execute(self, stmt):
        # First execute after load is DELETE stock_industry_board.
        self.deleted = True
        return None

    def scalar(self, query):
        self._scalar_calls += 1
        if self._scalar_calls == 1:
            return self.active_count
        return self.existing_count

    def scalars(self, query):
        return _FakeScalars([])


class TestLoadBoardsAndMembers:
    def test_auto_uses_ths_when_enough_members(self, monkeypatch):
        boards = [
            {
                "board_code": "THS881121",
                "board_name": "半导体",
                "source_code": "881121",
                "raw": {},
            }
        ]
        monkeypatch.setattr(
            "collector.industry_board_sync.fetch_ths_boards",
            lambda: boards,
        )
        symbols = [f"sz.{300000 + i:06d}" for i in range(120)]
        monkeypatch.setattr(
            "collector.industry_board_sync.fetch_ths_constituents",
            lambda code: symbols,
        )
        monkeypatch.setattr("collector.industry_board_sync.sleep_quietly", lambda s: None)

        source, board_rows, membership = _load_boards_and_members(
            _FakeSession(symbols),
            date(2026, 7, 9),
            source="auto",
            sleep_seconds=0,
        )
        assert source == "ths"
        assert board_rows[0]["source"] == "ths"
        assert len(membership) >= 100

    def test_auto_falls_back_to_sw_when_ths_fails(self, monkeypatch):
        monkeypatch.setattr(
            "collector.industry_board_sync.fetch_ths_boards",
            lambda: (_ for _ in ()).throw(RuntimeError("ths down")),
        )
        monkeypatch.setattr(
            "collector.industry_board_sync.fetch_sw_boards",
            lambda: [
                {
                    "board_code": "SW801016",
                    "board_name": "种植业",
                    "source_code": "801016",
                    "raw": {},
                }
            ],
        )
        monkeypatch.setattr(
            "collector.industry_board_sync.fetch_sw_constituents",
            lambda code: ["sh.600519"],
        )
        monkeypatch.setattr("collector.industry_board_sync.sleep_quietly", lambda s: None)

        source, board_rows, membership = _load_boards_and_members(
            _FakeSession(),
            date(2026, 7, 9),
            source="auto",
            sleep_seconds=0,
        )
        assert source == "sw"
        assert board_rows[0]["board_name"] == "种植业"
        assert "sh.600519" in membership


class TestSyncIndustryBoardsGuard:
    def test_refuses_to_wipe_existing_memberships_with_empty_fetch(self, monkeypatch):
        monkeypatch.setattr(
            "collector.industry_board_sync._load_boards_and_members",
            lambda *args, **kwargs: ("ths", [{"board_code": "THS1", "board_name": "银行"}], {}),
        )
        session = _WipeGuardSession(active_count=100, existing_count=50)

        with pytest.raises(IndustryBoardFetchError, match="Refusing to replace"):
            sync_industry_boards(session, date(2026, 7, 9), source="ths", sleep_seconds=0)

        assert session.deleted is False
        assert session.job is not None
        assert session.job.status == "failed"
        # Failure path commits job status only; membership wipe must not have run.
        assert session.committed is True
