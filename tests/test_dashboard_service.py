from app.services.dashboard_service import DashboardService


class TestDashboardService:
    def test_estimates_table_rows_from_postgres_stats(self):
        calls = []

        class FakeSession:
            def scalar(self, query, params=None):
                calls.append((str(query), params))
                return 20_000_000

        rows = DashboardService(FakeSession())._estimate_table_rows("kline_day")

        assert rows == 20_000_000
        assert calls[0][1] == {"table_name": "kline_day"}
        assert "pg_stat_user_tables" in calls[0][0]
        assert "pg_class" in calls[0][0]

    def test_estimates_table_rows_returns_none_when_stats_missing(self):
        class FakeSession:
            def scalar(self, _query, _params=None):
                return None

        rows = DashboardService(FakeSession())._estimate_table_rows("kline_day")

        assert rows is None
