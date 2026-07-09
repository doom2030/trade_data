import re

from pypinyin import Style, pinyin

LETTER_BUCKETS = ("A~E", "F~J", "K~O", "P~T", "U~Z")


def pinyin_initial(name: str) -> str:
    """Return uppercase Latin initial for an industry board name."""
    text = (name or "").strip()
    if not text:
        return "#"
    first = text[0]
    if first.isascii() and first.isalpha():
        return first.upper()
    if first.isdigit():
        return "#"
    initials = pinyin(first, style=Style.FIRST_LETTER, errors="ignore")
    if initials and initials[0] and initials[0][0]:
        letter = initials[0][0].upper()
        if "A" <= letter <= "Z":
            return letter
    return "#"


def letter_bucket(initial: str) -> str:
    letter = (initial or "#").upper()
    if letter < "A" or letter > "Z":
        return "U~Z"
    if letter <= "E":
        return "A~E"
    if letter <= "J":
        return "F~J"
    if letter <= "O":
        return "K~O"
    if letter <= "T":
        return "P~T"
    return "U~Z"


def normalize_em_code(code: str) -> str | None:
    """Map East Money 6-digit code to baostock symbol (sh./sz.). Skip BJ and others."""
    raw = str(code or "").strip()
    if not raw:
        return None
    if "." in raw:
        # already like sh.600000 or SZ.000001
        exchange, num = raw.split(".", 1)
        exchange = exchange.lower()
        if exchange in ("sh", "sz") and num.isdigit() and len(num) == 6:
            return f"{exchange}.{num}"
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 6:
        return None
    if digits.startswith(("5", "9")):
        # funds / other — out of scope
        return None
    if digits.startswith(("8", "4")):
        # Beijing exchange — out of scope
        return None
    if digits.startswith("6"):
        return f"sh.{digits}"
    if digits.startswith(("0", "3")):
        return f"sz.{digits}"
    return None
