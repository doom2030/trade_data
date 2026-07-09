import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.baostock_client import BaostockClient
from collector.cli_args import resolve_frequencies
from collector.collect_lock import acquire_collect_lock
from collector.kline_sync import update_weekly_monthly

app = typer.Typer()


@app.command()
def main(
    frequency: str = typer.Option(..., "--frequency"),
    end_date: str = typer.Option(None, "--end-date"),
):
    setup_logging()
    try:
        freqs = resolve_frequencies(frequency)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    if len(freqs) != 1 or freqs[0] not in ("week", "month"):
        raise typer.BadParameter("frequency must be week or month")
    frequency = freqs[0]
    end = date.fromisoformat(end_date) if end_date else date.today()
    session = SessionLocal()
    client = BaostockClient()
    try:
        with acquire_collect_lock(session) as acquired:
            if not acquired:
                typer.echo("Could not acquire collect lock, exiting")
                raise typer.Exit(1)
            job = update_weekly_monthly(session, client, frequency, end)
            typer.echo(f"Update {frequency}: job {job.id} status={job.status}")
    finally:
        client.logout()
        session.close()


if __name__ == "__main__":
    app()
