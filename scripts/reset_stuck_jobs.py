"""Fail orphaned running jobs and optionally release the collect lock."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.database import SessionLocal
from app.core.logging import setup_logging
from collector.collect_lock import collect_lock_holders, release_collect_lock_holders
from collector.job_helper import fail_interrupted_running_jobs

app = typer.Typer()


@app.command()
def main(
    grace_seconds: int = typer.Option(
        0,
        "--grace-seconds",
        help="只处理启动超过该秒数的 running 任务；0 表示全部",
    ),
    release_lock: bool = typer.Option(
        False,
        "--release-lock",
        help="同时强制释放 baostock 采集锁",
    ),
):
    setup_logging()
    session = SessionLocal()
    try:
        count = fail_interrupted_running_jobs(
            session,
            grace_seconds=grace_seconds,
            reason="Interrupted by process restart / manual reset",
        )
        session.commit()
        typer.echo(f"已将 {count} 个卡住的 running 任务标记为 failed")

        holders = collect_lock_holders(session)
        if holders:
            typer.echo(f"采集锁仍被占用（{len(holders)} 个会话）")
            for h in holders:
                typer.echo(
                    f"  pid={h.get('pid')} state={h.get('state')} "
                    f"app={h.get('application_name') or '-'}"
                )
            if release_lock:
                released = release_collect_lock_holders(session)
                typer.echo(f"已终止持锁后端: {released or '无'}")
                left = collect_lock_holders(session)
                if left:
                    typer.echo(f"仍有持锁会话: {left}")
                    raise typer.Exit(1)
                typer.echo("采集锁已释放")
            else:
                typer.echo("如需释放锁请加 --release-lock")
                raise typer.Exit(2)
        else:
            typer.echo("采集锁空闲")
    finally:
        session.close()


if __name__ == "__main__":
    app()
