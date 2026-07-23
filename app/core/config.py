from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    database_url: str = "postgresql+psycopg://trade:trade@localhost:5432/trade_data"

    default_history_start_date: str = "2023-01-01"
    default_history_end_date: str = ""
    # Trimmed product scope: day kline + forward adjust only.
    periodic_frequencies: str = "day"
    periodic_adjust_flags: str = "forward"
    default_adjust_flag: Literal["forward"] = "forward"
    backfill_priority: str = "day"

    collect_retry_times: int = 3
    collect_retry_sleep_seconds: int = 3
    collect_batch_size: int = 2000
    failed_job_retry_limit: int = 500
    failed_job_max_attempts: int = 3
    collect_global_lock_key: str = "trade_data_baostock_collect"

    trade_calendar_benchmark_symbols: str = (
        "sh.600519,sh.600036,sh.601318,sh.601398,sz.000001,sz.000333,"
        "sz.000858,sz.002594,sz.300750,sz.300760,sh.688981,sh.688111"
    )
    trade_calendar_min_valid_klines: int = 3
    catchup_daily_max_trading_days: int = 15
    manual_backfill_max_natural_days: int = 15

    api_max_kline_limit: int = 10000
    pending_job_runner_limit: int = 20
    pending_job_stale_minutes: int = 60
    disk_usage_warn_percent: int = 80
    disk_usage_critical_percent: int = 90

    secret_key: str = "dev-secret-change-in-production"
    admin_username: str = "admin"
    admin_password: str = "admin"
    session_max_age_hours: int = 72

    @property
    def benchmark_symbols(self) -> list[str]:
        return [s.strip() for s in self.trade_calendar_benchmark_symbols.split(",") if s.strip()]

    @property
    def adjust_flags(self) -> list[str]:
        return [s.strip() for s in self.periodic_adjust_flags.split(",") if s.strip()]

    @property
    def frequencies(self) -> list[str]:
        return [s.strip() for s in self.periodic_frequencies.split(",") if s.strip()]

    @property
    def backfill_priorities(self) -> list[str]:
        return [s.strip() for s in self.backfill_priority.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
