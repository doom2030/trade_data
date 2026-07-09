from app.core.config import get_settings

VALID_FREQUENCIES = frozenset({"day", "week", "month"})
VALID_ADJUST_FLAGS = frozenset({"none", "forward", "backward"})


def resolve_frequencies(value: str, *, allow_all: bool = False) -> list[str]:
    settings = get_settings()
    if allow_all and value == "all":
        return settings.backfill_priorities
    if value not in VALID_FREQUENCIES:
        allowed = "day, week, month" + (", all" if allow_all else "")
        raise ValueError(f"Invalid frequency '{value}'; allowed: {allowed}")
    return [value]


def resolve_adjust_flags(value: str, *, allow_all: bool = False) -> list[str]:
    settings = get_settings()
    if allow_all and value == "all":
        return settings.adjust_flags
    if value not in VALID_ADJUST_FLAGS:
        allowed = "none, forward, backward" + (", all" if allow_all else "")
        raise ValueError(f"Invalid adjust flag '{value}'; allowed: {allowed}")
    return [value]
