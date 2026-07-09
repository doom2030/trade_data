import re

BOARD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("sh_main", re.compile(r"^sh\.(600|601|603|605)\d{3}$")),
    ("sz_main", re.compile(r"^sz\.(000|001|002|003)\d{3}$")),
    ("chinext", re.compile(r"^sz\.300\d{3}$")),
    ("star", re.compile(r"^sh\.688\d{3}$")),
]


def classify_board(symbol: str) -> str | None:
    for board, pattern in BOARD_PATTERNS:
        if pattern.match(symbol):
            return board
    return None


def is_st_name(name: str) -> bool:
    upper = name.upper()
    return "ST" in upper or "*ST" in upper or upper.startswith("S")


def parse_symbol(code: str) -> tuple[str, str, str] | None:
    """Parse baostock code like sh.600000 into (symbol, exchange, code)."""
    if "." not in code:
        return None
    exchange, num = code.split(".", 1)
    if exchange not in ("sh", "sz") or not num.isdigit() or len(num) != 6:
        return None
    return code, exchange, num
