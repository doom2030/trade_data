from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockMaster(Base):
    __tablename__ = "stock_master"

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    exchange: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    board: Mapped[str] = mapped_column(Text, nullable=False)
    ipo_date: Mapped[date | None] = mapped_column(Date)
    out_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    security_type: Mapped[str] = mapped_column(Text, nullable=False, default="stock")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="baostock")
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("exchange", "code", name="uq_stock_master_exchange_code"),
        Index("idx_stock_master_board", "board"),
        Index("idx_stock_master_status", "status"),
    )


class StockStatusHistory(Base):
    __tablename__ = "stock_status_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(Text, ForeignKey("stock_master.symbol"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_stock_status_history_symbol", "symbol", "valid_from", "valid_to"),
        Index("idx_stock_status_history_status", "status", "valid_from", "valid_to"),
    )


class StockIndustryCurrent(Base):
    __tablename__ = "stock_industry_current"

    symbol: Mapped[str] = mapped_column(Text, ForeignKey("stock_master.symbol"), primary_key=True)
    industry_name: Mapped[str | None] = mapped_column(Text)
    industry_code: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="baostock")
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_stock_industry_current_name", "industry_name"),
        Index("idx_stock_industry_current_snapshot", "snapshot_date"),
    )


class IndustryBoard(Base):
    __tablename__ = "industry_board"

    board_code: Mapped[str] = mapped_column(Text, primary_key=True)
    board_name: Mapped[str] = mapped_column(Text, nullable=False)
    pinyin_initial: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="ths")
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_industry_board_name", "board_name"),
        Index("idx_industry_board_pinyin", "pinyin_initial"),
    )


class StockIndustryBoard(Base):
    __tablename__ = "stock_industry_board"

    symbol: Mapped[str] = mapped_column(Text, ForeignKey("stock_master.symbol"), primary_key=True)
    board_code: Mapped[str] = mapped_column(Text, ForeignKey("industry_board.board_code"), nullable=False)
    board_name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="ths")
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_stock_industry_board_code", "board_code"),
        Index("idx_stock_industry_board_name", "board_name"),
    )


class TradeCalendar(Base):
    __tablename__ = "trade_calendar"

    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    is_trading_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="baostock")
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("idx_trade_calendar_is_trading_day", "is_trading_day", "trade_date"),)


class StockSuspension(Base):
    __tablename__ = "stock_suspension"

    symbol: Mapped[str] = mapped_column(Text, ForeignKey("stock_master.symbol"), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="suspended")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="baostock_infer")
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_stock_suspension_trade_date", "trade_date"),
        Index("idx_stock_suspension_resolved", "resolved_at"),
    )


class KlineMixin:
    symbol: Mapped[str] = mapped_column(Text, ForeignKey("stock_master.symbol"), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True)
    adjust_flag: Mapped[str] = mapped_column(Text, primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    open: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    high: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    close: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    preclose: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    turn: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    pct_chg: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    tradestatus: Mapped[int | None] = mapped_column(Integer)
    is_st: Mapped[bool | None] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="baostock")
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KlineDay(Base, KlineMixin):
    __tablename__ = "kline_day"

    __table_args__ = (
        Index("idx_kline_day_symbol_date", "symbol", "trade_date"),
        Index("idx_kline_day_trade_date", "trade_date"),
        Index("idx_kline_day_adjust", "adjust_flag"),
    )


class KlineWeek(Base, KlineMixin):
    __tablename__ = "kline_week"

    __table_args__ = (
        Index("idx_kline_week_symbol_date", "symbol", "trade_date"),
        Index("idx_kline_week_trade_date", "trade_date"),
        Index("idx_kline_week_adjust", "adjust_flag"),
    )


class KlineMonth(Base, KlineMixin):
    __tablename__ = "kline_month"

    __table_args__ = (
        Index("idx_kline_month_symbol_date", "symbol", "trade_date"),
        Index("idx_kline_month_trade_date", "trade_date"),
        Index("idx_kline_month_adjust", "adjust_flag"),
    )


class CollectJob(Base):
    __tablename__ = "collect_job"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[str | None] = mapped_column(Text)
    adjust_flag: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    target_trade_date: Mapped[date | None] = mapped_column(Date)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    exhausted_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compensated_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_of_job_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("collect_job.id"))
    retry_of_item_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("collect_job_item.id"))
    params: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_collect_job_type_status", "job_type", "status"),
        Index("idx_collect_job_frequency", "frequency"),
        Index("idx_collect_job_created_at", "created_at"),
        Index("idx_collect_job_retry_of_item", "retry_of_item_id"),
    )


class CollectJobItem(Base):
    __tablename__ = "collect_job_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("collect_job.id"), nullable=False)
    symbol: Mapped[str | None] = mapped_column(Text, ForeignKey("stock_master.symbol"))
    frequency: Mapped[str | None] = mapped_column(Text)
    adjust_flag: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict | None] = mapped_column(JSONB)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_collect_job_item_job_id", "job_id"),
        Index("idx_collect_job_item_status", "status"),
        Index(
            "idx_collect_job_item_retry_lookup",
            "status",
            "frequency",
            "adjust_flag",
            "symbol",
            "start_date",
            "end_date",
        ),
    )


class QualityCheckResult(Base):
    __tablename__ = "quality_check_result"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("collect_job.id"))
    job_item_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("collect_job_item.id"))
    symbol: Mapped[str | None] = mapped_column(Text, ForeignKey("stock_master.symbol"))
    frequency: Mapped[str | None] = mapped_column(Text)
    adjust_flag: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    check_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    sample_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("idx_quality_check_result_job", "job_id", "job_item_id"),
        Index(
            "idx_quality_check_result_symbol",
            "symbol",
            "frequency",
            "adjust_flag",
            "start_date",
            "end_date",
        ),
        Index("idx_quality_check_result_status", "status", "severity", "check_type"),
    )
