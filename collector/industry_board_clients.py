"""Industry board data clients: Tonghuashun primary, Shenwan fallback."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import akshare as ak
import requests

from collector.industry_board_utils import normalize_em_code

logger = logging.getLogger(__name__)

THS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://q.10jqka.com.cn/",
    "Accept": "*/*",
}


class IndustryBoardFetchError(RuntimeError):
    pass


def fetch_ths_boards() -> list[dict[str, Any]]:
    """Return Tonghuashun industry boards: [{board_code, board_name, raw}]."""
    try:
        df = ak.stock_board_industry_name_ths()
    except Exception as e:
        raise IndustryBoardFetchError(f"THS board list failed: {e}") from e
    if df is None or df.empty:
        raise IndustryBoardFetchError("THS board list is empty")

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        name = str(row.get("name") or "").strip()
        code = str(row.get("code") or "").strip()
        if not name or not code:
            continue
        rows.append(
            {
                "board_code": f"THS{code}",
                "board_name": name,
                "source_code": code,
                "raw": {k: _jsonable(v) for k, v in row.to_dict().items()},
            }
        )
    if not rows:
        raise IndustryBoardFetchError("THS board list parsed empty")
    return rows


def fetch_ths_constituents(source_code: str, *, page_size: int = 500) -> list[str]:
    """Return baostock-style symbols for a THS industry board code (e.g. 881121)."""
    url = f"https://d.10jqka.com.cn/v2/blockrank/{source_code}/199112/d{page_size}.js"
    try:
        resp = requests.get(url, headers=THS_HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise IndustryBoardFetchError(f"THS constituents failed for {source_code}: {e}") from e

    match = re.search(r"quotebridge_\w+\((.*)\)\s*$", resp.text, re.S)
    if not match:
        raise IndustryBoardFetchError(f"THS constituents payload invalid for {source_code}")

    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        raise IndustryBoardFetchError(f"THS constituents JSON invalid for {source_code}: {e}") from e

    items = payload.get("items") or []
    symbols: list[str] = []
    for item in items:
        code = str(item.get("5") or "").strip()
        symbol = normalize_em_code(code)
        if symbol:
            symbols.append(symbol)
    return symbols


def fetch_sw_boards() -> list[dict[str, Any]]:
    """Return Shenwan L2 industry boards."""
    try:
        df = ak.sw_index_second_info()
    except Exception as e:
        raise IndustryBoardFetchError(f"SW board list failed: {e}") from e
    if df is None or df.empty:
        raise IndustryBoardFetchError("SW board list is empty")

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        name = str(row.get("行业名称") or "").strip()
        raw_code = str(row.get("行业代码") or "").strip()
        code = raw_code.split(".")[0]
        if not name or not code:
            continue
        rows.append(
            {
                "board_code": f"SW{code}",
                "board_name": name,
                "source_code": code,
                "raw": {k: _jsonable(v) for k, v in row.to_dict().items()},
            }
        )
    if not rows:
        raise IndustryBoardFetchError("SW board list parsed empty")
    return rows


def fetch_sw_constituents(source_code: str) -> list[str]:
    """Return baostock-style symbols for a Shenwan industry code (e.g. 801016)."""
    code = source_code.split(".")[0]
    try:
        df = ak.index_component_sw(code)
    except Exception as e:
        raise IndustryBoardFetchError(f"SW constituents failed for {code}: {e}") from e
    if df is None or df.empty:
        return []

    code_col = "证券代码" if "证券代码" in df.columns else None
    if not code_col:
        # unexpected shape
        raise IndustryBoardFetchError(f"SW constituents missing 证券代码 for {code}")

    symbols: list[str] = []
    for raw in df[code_col].tolist():
        symbol = normalize_em_code(str(raw))
        if symbol:
            symbols.append(symbol)
    return symbols


def _jsonable(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def sleep_quietly(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)
