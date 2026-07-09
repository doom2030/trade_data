from collector.collect_lock import (
    _lock_blocking,
    _lock_class_obj,
    _lock_id,
    format_lock_contention_message,
)


class _FakeConn:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return self

    def scalar(self):
        return True


class TestCollectLockHelpers:
    def test_lock_id_stable(self):
        a = _lock_id("trade_data_baostock_collect")
        b = _lock_id("trade_data_baostock_collect")
        assert a == b
        assert isinstance(a, int)

    def test_lock_class_obj_in_uint32_range(self):
        classid, objid = _lock_class_obj(_lock_id("trade_data_baostock_collect"))
        assert 0 <= classid <= 0xFFFFFFFF
        assert 0 <= objid <= 0xFFFFFFFF

    def test_contention_message_mentions_leak_recovery(self):
        msg = format_lock_contention_message()
        assert "采集锁" in msg
        assert "--release" in msg

    def test_lock_blocking_sets_timeout_without_bind_params(self):
        conn = _FakeConn()
        assert _lock_blocking(conn, lock_id=123, timeout_seconds=600) is True
        assert any("SET lock_timeout = 600000" in s for s in conn.statements)
        assert any("SET lock_timeout = 0" in s for s in conn.statements)
        assert not any(":timeout" in s for s in conn.statements)
