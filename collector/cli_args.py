from app.core.config import get_settings

# Product collection scope: day kline + forward adjust only.
VALID_FREQUENCIES = frozenset({"day"})
VALID_ADJUST_FLAGS = frozenset({"forward"})


def resolve_frequencies(value: str, *, allow_all: bool = False) -> list[str]:
    settings = get_settings()
    if allow_all and value == "all":
        return settings.backfill_priorities
    if value not in VALID_FREQUENCIES:
        allowed = ", ".join(sorted(VALID_FREQUENCIES)) + (", all" if allow_all else "")
        raise ValueError(f"Invalid frequency '{value}'; allowed: {allowed}")
    configured = set(settings.frequencies) or {"day"}
    if value not in configured:
        raise ValueError(
            f"Frequency '{value}' is disabled by PERIODIC_FREQUENCIES={settings.periodic_frequencies}"
        )
    return [value]


def resolve_adjust_flags(value: str, *, allow_all: bool = False) -> list[str]:
    settings = get_settings()
    if allow_all and value == "all":
        return settings.adjust_flags
    if value not in VALID_ADJUST_FLAGS:
        allowed = ", ".join(sorted(VALID_ADJUST_FLAGS)) + (", all" if allow_all else "")
        raise ValueError(f"Invalid adjust flag '{value}'; allowed: {allowed}")
    configured = set(settings.adjust_flags) or {"forward"}
    if value not in configured:
        raise ValueError(
            f"Adjust '{value}' is disabled by PERIODIC_ADJUST_FLAGS={settings.periodic_adjust_flags}"
        )
    return [value]
