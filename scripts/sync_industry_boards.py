import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.industry_board_sync import sync_industry_boards

app = typer.Typer()


@app.command()
def main(
    snapshot_date: str = typer.Option(None, "--snapshot-date"),
    sleep: float = typer.Option(0.35, "--sleep", help="Seconds between remote requests"),
    source: str = typer.Option(
        "auto",
        "--source",
        help="auto (THS then Shenwan fallback) | ths | sw",
    ),
):
    setup_logging()
    snap = date.fromisoformat(snapshot_date) if snapshot_date else date.today()
    session = SessionLocal()
    try:
        boards, members, used = sync_industry_boards(
            session,
            snap,
            sleep_seconds=sleep,
            source=source,
        )
        typer.echo(
            f"Synced {boards} industry boards, {members} stock memberships (source={used})"
        )
    finally:
        session.close()


if __name__ == "__main__":
    app()
