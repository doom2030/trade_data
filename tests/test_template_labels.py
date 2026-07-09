from app.core.templates import JOB_TYPE_LABELS, job_type_label


class TestJobTypeLabel:
    def test_known_types_have_chinese(self):
        assert job_type_label("sync_industry") == "同步证监会行业"
        assert job_type_label("backfill_kline") == "历史 K 线回填"
        assert job_type_label("sync_industry_boards") == "同步行业板块"

    def test_unknown_type_falls_back_to_code(self):
        assert job_type_label("custom_future_job") == "custom_future_job"

    def test_filter_options_cover_readme_types(self):
        required = {
            "sync_stock_meta",
            "sync_industry",
            "sync_industry_boards",
            "sync_trade_calendar",
            "backfill_kline",
            "daily_update",
            "quality_check",
        }
        assert required.issubset(JOB_TYPE_LABELS.keys())
