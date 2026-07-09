import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.baostock_client import BaostockClient
from collector.collect_lock import acquire_collect_lock
from collector.stock_meta_sync import sync_stock_meta

app = typer.Typer()


@app.command()
def main(
    snapshot_date: str = typer.Option(None, "--snapshot-date"),
):
    setup_logging()
    snap = date.fromisoformat(snapshot_date) if snapshot_date else date.today()
    session = SessionLocal()
    client = BaostockClient()
    try:
        with acquire_collect_lock(session) as acquired:
            if not acquired:
                typer.echo("Could not acquire collect lock, exiting")
                raise typer.Exit(1)
            count = sync_stock_meta(session, client, snap)
            typer.echo(f"Synced {count} stocks")
    finally:
        client.logout()
        session.close()


if __name__ == "__main__":
    app()
