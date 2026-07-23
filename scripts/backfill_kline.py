import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.baostock_client import BaostockClient
from collector.cli_args import resolve_adjust_flags, resolve_frequencies
from collector.collect_lock import acquire_collect_lock, format_lock_contention_message
from collector.kline_sync import backfill_klines

app = typer.Typer()
settings = get_settings()


@app.command()
def main(
    frequency: str = typer.Option("day", "--frequency", help="仅支持 day（产品范围）"),
    adjust: str = typer.Option("forward", "--adjust", help="仅支持 forward（产品范围）"),
    start_date: str = typer.Option(
        None,
        "--start-date",
        help=f"默认 {settings.default_history_start_date}",
    ),
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
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--no-skip-existing",
        help="默认跳过已入库区间，只请求缺口",
    ),
):
    """历史日 K（前复权）回填；可中断续跑。"""
    setup_logging()
    try:
        freqs = resolve_frequencies(frequency, allow_all=False)
        adjs = resolve_adjust_flags(adjust, allow_all=False)
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
                job = backfill_klines(
                    session,
                    client,
                    freq,
                    adjs,
                    start,
                    end,
                    symbols,
                    skip_existing=skip_existing,
                )
                typer.echo(
                    f"Backfill {freq}/{','.join(adjs)}: job {job.id} status={job.status} "
                    f"success={job.success_items} skipped={job.skipped_items} "
                    f"failed={job.failed_items} skip_existing={skip_existing}"
                )
    finally:
        client.logout()
        session.close()


if __name__ == "__main__":
    app()
