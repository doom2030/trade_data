import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.baostock_client import BaostockClient
from collector.collect_lock import acquire_collect_lock
from collector.trade_calendar_sync import sync_trade_calendar

app = typer.Typer()


@app.command()
def main(
    start_date: str = typer.Option(..., "--start-date"),
    end_date: str = typer.Option(..., "--end-date"),
):
    setup_logging()
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    session = SessionLocal()
    client = BaostockClient()
    try:
        with acquire_collect_lock(session) as acquired:
            if not acquired:
                typer.echo("Could not acquire collect lock, exiting")
                raise typer.Exit(1)
            count = sync_trade_calendar(session, client, start, end)
            typer.echo(f"Synced {count} calendar days")
    finally:
        client.logout()
        session.close()


if __name__ == "__main__":
    app()
