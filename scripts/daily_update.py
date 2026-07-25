import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.logging import setup_logging
from collector.daily_update_runner import run_daily_update

app = typer.Typer()


@app.command()
def main(
    trade_date: str = typer.Option(None, "--trade-date"),
):
    setup_logging()
    target = date.fromisoformat(trade_date) if trade_date else None
    result = run_daily_update(target)
    if result.skipped_lock:
        typer.echo(result.message or "Could not acquire collect lock, exiting")
        raise typer.Exit(1)
    if result.message:
        typer.echo(result.message)
    if result.non_trading_day:
        raise typer.Exit(0)
    if not result.ok:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
