from pathlib import Path
from urllib.parse import quote

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["quote_path"] = lambda s: quote(str(s), safe="")

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


def board_label(code: str) -> str:
    return BOARD_LABELS.get(code, code)


def status_label(code: str) -> str:
    return STATUS_LABELS.get(code, code)


def frequency_label(code: str) -> str:
    return FREQUENCY_LABELS.get(code, code)


def adjust_label(code: str) -> str:
    return ADJUST_LABELS.get(code, code)


def at_least(value: int, minimum: int = 0) -> int:
    return max(value, minimum)


templates.env.globals["board_label"] = board_label
templates.env.globals["status_label"] = status_label
templates.env.globals["frequency_label"] = frequency_label
templates.env.globals["adjust_label"] = adjust_label
templates.env.globals["at_least"] = at_least
