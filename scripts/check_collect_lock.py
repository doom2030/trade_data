"""Show / force-release the baostock collect advisory lock."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.collect_lock import (
    collect_lock_holders,
    format_lock_contention_message,
    release_collect_lock_holders,
)

app = typer.Typer()


@app.command()
def main(
    release: bool = typer.Option(
        False,
        "--release",
        help="强制断开持锁后端（用于连接池泄漏导致的死锁恢复）",
    ),
):
    setup_logging()
    session = SessionLocal()
    try:
        holders = collect_lock_holders(session)
        if not holders:
            typer.echo("采集锁空闲（当前无持锁会话）")
            raise typer.Exit(0)

        typer.echo(f"采集锁被占用，共 {len(holders)} 个会话：")
        for h in holders:
            typer.echo(
                f"  pid={h.get('pid')} state={h.get('state')} "
                f"app={h.get('application_name') or '-'} "
                f"since={h.get('query_start')} query={h.get('query')}"
            )

        if not release:
            typer.echo("")
            typer.echo(format_lock_contention_message(session))
            typer.echo("如需强制释放: python scripts/check_collect_lock.py --release")
            raise typer.Exit(2)

        released = release_collect_lock_holders(session)
        typer.echo(f"已终止持锁后端: {released or '无'}")
        left = collect_lock_holders(session)
        if left:
            typer.echo(f"仍有持锁会话: {left}")
            raise typer.Exit(1)
        typer.echo("采集锁已释放")
        raise typer.Exit(0)
    finally:
        session.close()


if __name__ == "__main__":
    app()
