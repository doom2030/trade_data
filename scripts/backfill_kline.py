import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.baostock_client import BaostockClient
from collector.cli_args import resolve_adjust_flags, resolve_frequencies
from collector.collect_lock import acquire_collect_lock, format_lock_contention_message
from collector.kline_sync import backfill_klines

app = typer.Typer()


@app.command()
def main(
    frequency: str = typer.Option("all", "--frequency"),
    adjust: str = typer.Option("all", "--adjust"),
    start_date: str = typer.Option(None, "--start-date"),
    end_date: str = typer.Option(None, "--end-date"),
    symbol: str = typer.Option(None, "--symbol"),
    wait: bool = typer.Option(
        False,
        "--wait/--no-wait",
        help="等待采集锁（pending-worker 占用时不要立刻退出）",
    ),
    wait_seconds: int = typer.Option(
        600,
        "--wait-seconds",
        help="等待采集锁的最长时间（秒），仅 --wait 时生效",
    ),
):
    setup_logging()
    try:
        freqs = resolve_frequencies(frequency, allow_all=True)
        adjs = resolve_adjust_flags(adjust, allow_all=True)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    symbols = [symbol] if symbol else None

    session = SessionLocal()
    client = BaostockClient()
    try:
        with acquire_collect_lock(
            session,
            wait=wait,
            timeout_seconds=wait_seconds if wait else None,
        ) as acquired:
            if not acquired:
                typer.echo(format_lock_contention_message(session))
                typer.echo("提示: 加 --wait 可排队等待锁；或先等 pending-worker 跑完当前任务。")
                raise typer.Exit(1)
            for freq in freqs:
                job = backfill_klines(session, client, freq, adjs, start, end, symbols)
                typer.echo(f"Backfill {freq}: job {job.id} status={job.status}")
    finally:
        client.logout()
        session.close()


if __name__ == "__main__":
    app()
