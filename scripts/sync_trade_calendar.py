import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.baostock_client import BaostockClient
from collector.collect_lock import acquire_collect_lock
from collector.trade_calendar_sync import sync_trade_calendar

app = typer.Typer()
settings = get_settings()


def default_calendar_range(today: date | None = None) -> tuple[date, date]:
    current = today or date.today()
    return date.fromisoformat(settings.default_history_start_date), date(current.year + 1, 12, 31)


def resolve_calendar_range(start_date: str | None, end_date: str | None) -> tuple[date, date]:
    default_start, default_end = default_calendar_range()
    start = date.fromisoformat(start_date) if start_date else default_start
    end = date.fromisoformat(end_date) if end_date else default_end
    if end < start:
        raise typer.BadParameter("end-date must be >= start-date")
    return start, end


@app.command()
def main(
    start_date: str = typer.Option(None, "--start-date"),
    end_date: str = typer.Option(None, "--end-date"),
):
    setup_logging()
    start, end = resolve_calendar_range(start_date, end_date)
    session = SessionLocal()
    client = BaostockClient()
    try:
        with acquire_collect_lock(session) as acquired:
            if not acquired:
                typer.echo("Could not acquire collect lock, exiting")
                raise typer.Exit(1)
            count = sync_trade_calendar(session, client, start, end)
            typer.echo(f"Synced {count} calendar days ({start}..{end})")
    finally:
        client.logout()
        session.close()


if __name__ == "__main__":
    app()
