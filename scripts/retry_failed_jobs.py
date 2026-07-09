import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.baostock_client import BaostockClient
from collector.collect_lock import acquire_collect_lock
from collector.retry_service import retry_failed_items

app = typer.Typer()
settings = get_settings()


@app.command()
def main(
    max_attempts: int = typer.Option(3, "--max-attempts"),
    limit: int = typer.Option(500, "--limit"),
):
    setup_logging()
    session = SessionLocal()
    client = BaostockClient()
    try:
        with acquire_collect_lock(session) as acquired:
            if not acquired:
                typer.echo("Could not acquire collect lock, exiting")
                raise typer.Exit(1)
            count = retry_failed_items(session, client, max_attempts, limit)
            typer.echo(f"Retried {count} failed items")
    finally:
        client.logout()
        session.close()


if __name__ == "__main__":
    app()
