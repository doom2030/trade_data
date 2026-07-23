import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import baostock as bs
from tenacity import retry, stop_after_attempt, wait_fixed

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

ADJUST_MAP = {"none": "3", "forward": "2", "backward": "1"}
FREQ_MAP = {"day": "d"}


class BaostockError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"baostock error {code}: {message}")


def _empty_to_none(value: Any) -> Any:
    if value is None or value == "":
        return None
    return value


def _to_decimal(value: Any) -> Decimal | None:
    value = _empty_to_none(value)
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _to_date(value: Any) -> date | None:
    value = _empty_to_none(value)
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _to_int(value: Any) -> int | None:
    value = _empty_to_none(value)
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _to_bool(value: Any) -> bool | None:
    value = _empty_to_none(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "yes")


class BaostockClient:
    def __init__(self):
        self._logged_in = False

    def login(self) -> None:
        if self._logged_in:
            return
        lg = bs.login()
        if lg.error_code != "0":
            raise BaostockError(lg.error_code, lg.error_msg)
        self._logged_in = True
        logger.info("baostock login success")

    def logout(self) -> None:
        if not self._logged_in:
            return
        bs.logout()
        self._logged_in = False
        logger.info("baostock logout")

    @retry(
        stop=stop_after_attempt(settings.collect_retry_times),
        wait=wait_fixed(settings.collect_retry_sleep_seconds),
        reraise=True,
    )
    def query_stock_basic(self, snapshot_date: date | None = None) -> list[dict]:
        self.login()
        rs = bs.query_stock_basic()
        if rs.error_code != "0":
            raise BaostockError(rs.error_code, rs.error_msg)
        rows = []
        while rs.next():
            row = rs.get_row_data()
            fields = rs.fields
            raw = dict(zip(fields, row, strict=False))
            rows.append(
                {
                    "code": raw.get("code"),
                    "code_name": raw.get("code_name"),
                    "ipo_date": _to_date(raw.get("ipoDate")),
                    "out_date": _to_date(raw.get("outDate")),
                    "type": raw.get("type"),
                    "status": raw.get("status"),
                    "raw_payload": raw,
                }
            )
        return rows

    @retry(
        stop=stop_after_attempt(settings.collect_retry_times),
        wait=wait_fixed(settings.collect_retry_sleep_seconds),
        reraise=True,
    )
    def query_industry(self, snapshot_date: date | None = None) -> list[dict]:
        self.login()
        day = (snapshot_date or date.today()).strftime("%Y-%m-%d")
        rs = bs.query_stock_industry()
        if rs.error_code != "0":
            raise BaostockError(rs.error_code, rs.error_msg)
        rows = []
        while rs.next():
            row = rs.get_row_data()
            fields = rs.fields
            raw = dict(zip(fields, row, strict=False))
            rows.append(
                {
                    "code": raw.get("code"),
                    "code_name": raw.get("code_name"),
                    "industry": raw.get("industry"),
                    "industryClassification": raw.get("industryClassification"),
                    "snapshot_date": day,
                    "raw_payload": raw,
                }
            )
        return rows

    @retry(
        stop=stop_after_attempt(settings.collect_retry_times),
        wait=wait_fixed(settings.collect_retry_sleep_seconds),
        reraise=True,
    )
    def query_trade_calendar(self, start_date: date, end_date: date) -> list[dict]:
        self.login()
        rs = bs.query_trade_dates(
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
        )
        if rs.error_code != "0":
            raise BaostockError(rs.error_code, rs.error_msg)
        rows = []
        while rs.next():
            row = rs.get_row_data()
            fields = rs.fields
            raw = dict(zip(fields, row, strict=False))
            cal_date = _to_date(raw.get("calendar_date"))
            is_trading = raw.get("is_trading_day") == "1"
            if cal_date:
                rows.append(
                    {
                        "trade_date": cal_date,
                        "is_trading_day": is_trading,
                        "raw_payload": raw,
                    }
                )
        return rows

    @retry(
        stop=stop_after_attempt(settings.collect_retry_times),
        wait=wait_fixed(settings.collect_retry_sleep_seconds),
        reraise=True,
    )
    def query_kline(
        self,
        symbol: str,
        frequency: str,
        start_date: date,
        end_date: date,
        adjust_flag: str,
    ) -> list[dict]:
        self.login()
        freq = FREQ_MAP.get(frequency)
        adj = ADJUST_MAP.get(adjust_flag)
        if not freq or not adj:
            raise ValueError(f"Invalid frequency={frequency} or adjust_flag={adjust_flag}")

        fields = (
            "date,code,open,high,low,close,preclose,volume,amount,"
            "adjustflag,turn,tradestatus,pctChg,isST"
        )
        rs = bs.query_history_k_data_plus(
            symbol,
            fields,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            frequency=freq,
            adjustflag=adj,
        )
        if rs.error_code != "0":
            raise BaostockError(rs.error_code, rs.error_msg)

        rows = []
        while rs.next():
            row = rs.get_row_data()
            field_list = rs.fields
            raw = dict(zip(field_list, row, strict=False))
            trade_date = _to_date(raw.get("date"))
            if not trade_date:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "open": _to_decimal(raw.get("open")),
                    "high": _to_decimal(raw.get("high")),
                    "low": _to_decimal(raw.get("low")),
                    "close": _to_decimal(raw.get("close")),
                    "preclose": _to_decimal(raw.get("preclose")),
                    "volume": _to_decimal(raw.get("volume")),
                    "amount": _to_decimal(raw.get("amount")),
                    "turn": _to_decimal(raw.get("turn")),
                    "pct_chg": _to_decimal(raw.get("pctChg")),
                    "tradestatus": _to_int(raw.get("tradestatus")),
                    "is_st": _to_bool(raw.get("isST")),
                    "adjust_flag": adjust_flag,
                    "raw_payload": raw,
                }
            )
        return rows
