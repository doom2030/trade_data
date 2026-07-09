from unittest.mock import patch

from app.api.routes_health import _migration_status, _schema_ready
from app.core.migrations import expected_migration_head


class TestSchemaReady:
    def test_returns_false_when_table_missing(self):
        existing = {"alembic_version", "collect_job", "collect_job_item", "trade_calendar"}

        class FakeSession:
            def scalar(self, _query, params):
                return params["name"] in existing

        assert _schema_ready(FakeSession()) is False

    def test_returns_true_when_all_tables_exist(self):
        from app.api.routes_health import REQUIRED_TABLES

        class FakeSession:
            def scalar(self, _query, params):
                return params["name"] in REQUIRED_TABLES

        assert _schema_ready(FakeSession()) is True


class TestMigrationStatus:
    def test_ok_when_current_matches_head(self):
        class FakeSession:
            def scalar(self, _query, params=None):
                return "002"

        with patch("app.api.routes_health.expected_migration_head", return_value="002"):
            status, current, expected = _migration_status(FakeSession())
        assert status == "ok"
        assert current == "002"
        assert expected == "002"

    def test_behind_when_current_is_older(self):
        class FakeSession:
            def scalar(self, _query, params=None):
                return "001"

        with patch("app.api.routes_health.expected_migration_head", return_value="002"):
            status, current, expected = _migration_status(FakeSession())
        assert status == "behind"
        assert current == "001"
        assert expected == "002"

    def test_expected_head_matches_repository(self):
        assert expected_migration_head() == "002"
