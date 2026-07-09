from datetime import datetime, timezone

from app.models import KlineDay, KlineMonth, KlineWeek

KLINE_MODELS = {
    "day": KlineDay,
    "week": KlineWeek,
    "month": KlineMonth,
}


def get_kline_model(frequency: str):
    model = KLINE_MODELS.get(frequency)
    if model is None:
        raise ValueError(f"Unknown frequency: {frequency}")
    return model


def make_period_start(trade_date) -> datetime:
    return datetime(trade_date.year, trade_date.month, trade_date.day, tzinfo=timezone.utc)
