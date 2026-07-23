from datetime import date

from pydantic import BaseModel


class KlineItemOut(BaseModel):
    time: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None
    turn: float | None = None


class SuspensionOut(BaseModel):
    date: str
    reason: str
    source: str
    resolved: bool


class KlineResponse(BaseModel):
    symbol: str
    frequency: str
    adjust: str
    items: list[KlineItemOut]
    suspensions: list[SuspensionOut] = []


class BackfillRequest(BaseModel):
    symbol: str
    frequency: str
    start: date
    end: date


class BackfillResponse(BaseModel):
    job_id: int
    status: str
    job_type: str
    symbol: str
    frequency: str
    start: str
    end: str
    adjust_flags: list[str]
