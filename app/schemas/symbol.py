from datetime import date

from pydantic import BaseModel


class SymbolOut(BaseModel):
    symbol: str
    exchange: str
    code: str
    name: str
    board: str
    ipo_date: date | None = None
    out_date: date | None = None
    status: str
    current_industry: str | None = None

    model_config = {"from_attributes": True}


class IndustryOut(BaseModel):
    industry_name: str
    symbol_count: int


class IndustrySymbolOut(BaseModel):
    symbol: str
    name: str
    board: str
    status: str
