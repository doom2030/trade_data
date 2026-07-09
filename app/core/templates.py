from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["quote_path"] = lambda s: quote(str(s), safe="")

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")


def format_datetime(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(DISPLAY_TZ).strftime(fmt)

BOARD_LABELS = {
    "sh_main": "上证主板",
    "sz_main": "深证主板",
    "chinext": "创业板",
    "star": "科创板",
}

STATUS_LABELS = {
    "active": "正常",
    "excluded": "已排除",
    "inactive": "退市",
    "pending": "等待中",
    "running": "运行中",
    "success": "成功",
    "partial_success": "部分成功",
    "failed": "失败",
    "cancelled": "已取消",
    "exhausted": "已耗尽",
    "compensated": "已补偿",
    "skipped": "已跳过",
}

FREQUENCY_LABELS = {"day": "日线", "week": "周线", "month": "月线"}
ADJUST_LABELS = {"none": "不复权", "forward": "前复权", "backward": "后复权"}

JOB_TYPE_LABELS = {
    "sync_stock_meta": "同步股票池",
    "sync_industry": "同步证监会行业",
    "sync_industry_boards": "同步行业板块",
    "sync_trade_calendar": "同步交易日历",
    "backfill_kline": "历史 K 线回填",
    "daily_update": "日线日常更新",
    "catchup_daily_update": "缺失交易日补齐",
    "update_weekly": "周线更新",
    "update_monthly": "月线更新",
    "retry_failed_jobs": "批量失败补偿",
    "manual_retry_failed_job": "手动重试任务",
    "manual_retry_failed_item": "手动重试明细",
    "manual_backfill_range": "手动区间补采",
    "quality_check": "质量检查",
}


def board_label(code: str) -> str:
    return BOARD_LABELS.get(code, code)


def status_label(code: str) -> str:
    return STATUS_LABELS.get(code, code)


def frequency_label(code: str) -> str:
    return FREQUENCY_LABELS.get(code, code)


def adjust_label(code: str) -> str:
    return ADJUST_LABELS.get(code, code)


def job_type_label(code: str) -> str:
    return JOB_TYPE_LABELS.get(code, code)


def at_least(value: int, minimum: int = 0) -> int:
    return max(value, minimum)


templates.env.globals["board_label"] = board_label
templates.env.globals["status_label"] = status_label
templates.env.globals["frequency_label"] = frequency_label
templates.env.globals["adjust_label"] = adjust_label
templates.env.globals["job_type_label"] = job_type_label
templates.env.globals["at_least"] = at_least
templates.env.globals["format_datetime"] = format_datetime
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["job_type_label"] = job_type_label
