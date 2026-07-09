import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.baostock_client import BaostockClient
from collector.pending_job_runner import run_loop, run_pending_jobs

app = typer.Typer()
settings = get_settings()


@app.command()
def main(
    limit: int = typer.Option(20, "--limit"),
    loop: bool = typer.Option(False, "--loop"),
    sleep: int = typer.Option(10, "--sleep"),
):
    setup_logging()
    if loop:
        run_loop(sleep_seconds=sleep, limit=limit)
    else:
        session = SessionLocal()
        client = BaostockClient()
        try:
            count = run_pending_jobs(session, client, limit)
            typer.echo(f"Executed {count} pending jobs")
        finally:
            client.logout()
            session.close()


if __name__ == "__main__":
    app()
