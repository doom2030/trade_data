from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import StockSuspension
from app.schemas.kline import KlineItemOut, KlineResponse, SuspensionOut
from collector.kline_table_router import get_kline_model

settings = get_settings()


def _to_float(val: Decimal | None) -> float | None:
    if val is None:
        return None
    return float(val)


class KlineQueryService:
    def __init__(self, db: Session):
        self.db = db

    def query_klines(
        self,
        frequency: str,
        symbol: str,
        start: date,
        end: date,
        adjust: str,
    ) -> KlineResponse:
        if frequency not in ("day", "week", "month"):
            raise HTTPException(400, "Invalid frequency")
        if adjust not in ("none", "forward", "backward"):
            raise HTTPException(400, "Invalid adjust flag")
        if end < start:
            raise HTTPException(400, "end must be >= start")

        model = get_kline_model(frequency)

        count = self.db.scalar(
            select(func.count())
            .select_from(model)
            .where(
                model.symbol == symbol,
                model.trade_date >= start,
                model.trade_date <= end,
                model.adjust_flag == adjust,
            )
        )
        if count and count > settings.api_max_kline_limit:
            raise HTTPException(
                400,
                f"Query would return {count} rows, exceeding limit of {settings.api_max_kline_limit}",
            )

        rows = self.db.scalars(
            select(model)
            .where(
                model.symbol == symbol,
                model.trade_date >= start,
                model.trade_date <= end,
                model.adjust_flag == adjust,
            )
            .order_by(model.trade_date)
        ).all()

        items = [
            KlineItemOut(
                time=row.trade_date.isoformat(),
                open=_to_float(row.open),
                high=_to_float(row.high),
                low=_to_float(row.low),
                close=_to_float(row.close),
                volume=_to_float(row.volume),
                amount=_to_float(row.amount),
            )
            for row in rows
        ]

        suspensions: list[SuspensionOut] = []
        if frequency == "day":
            susp_rows = self.db.scalars(
                select(StockSuspension).where(
                    StockSuspension.symbol == symbol,
                    StockSuspension.trade_date >= start,
                    StockSuspension.trade_date <= end,
                )
            ).all()
            suspensions = [
                SuspensionOut(
                    date=s.trade_date.isoformat(),
                    reason=s.reason,
                    source=s.source,
                    resolved=s.resolved_at is not None,
                )
                for s in susp_rows
            ]

        return KlineResponse(
            symbol=symbol,
            frequency=frequency,
            adjust=adjust,
            items=items,
            suspensions=suspensions,
        )
