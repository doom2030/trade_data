import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging
from app.models import CollectJob
from collector.baostock_client import BaostockClient
from collector.collect_lock import acquire_collect_lock
from collector.job_helper import append_job_log
from collector.kline_sync import (
    create_catchup_jobs,
    daily_update_klines,
    get_missed_trading_days,
    is_trading_day,
)
from collector.quality_check import run_quality_check
from collector.retry_service import retry_failed_items
from collector.stock_meta_sync import sync_stock_meta
from collector.trade_calendar_sync import ensure_trade_calendar_for_date

app = typer.Typer()
settings = get_settings()


def _echo_job_summary(job: CollectJob) -> None:
    typer.echo(
        f"Daily update job {job.id} status={job.status} "
        f"total={job.total_items} success={job.success_items} "
        f"failed={job.failed_items} skipped={job.skipped_items} "
        f"inserted={job.inserted_rows} updated={job.updated_rows}"
    )


@app.command()
def main(
    trade_date: str = typer.Option(None, "--trade-date"),
):
    setup_logging()
    target = date.fromisoformat(trade_date) if trade_date else date.today()
    session = SessionLocal()
    client = BaostockClient()
    try:
        with acquire_collect_lock(session) as acquired:
            if not acquired:
                typer.echo("Could not acquire collect lock, exiting")
                raise typer.Exit(1)

            ensure_trade_calendar_for_date(session, client, target)

            if not is_trading_day(session, target):
                job = daily_update_klines(session, client, target)
                append_job_log(
                    session,
                    job,
                    "日更跳过：非交易日",
                    payload=(job.params or {}).get("summary"),
                )
                session.commit()
                _echo_job_summary(job)
                raise typer.Exit(0)

            retry_failed_items(session, client, settings.failed_job_max_attempts, settings.failed_job_retry_limit)

            missed = get_missed_trading_days(session, target)
            if missed:
                job_ids = create_catchup_jobs(session, missed)
                typer.echo(f"Created {len(job_ids)} catchup jobs for {len(missed)} missed days")

            sync_stock_meta(session, client, target)

            job = daily_update_klines(session, client, target)
            run_quality_check(session, job.id)
            job = session.get(CollectJob, job.id)
            if job:
                append_job_log(
                    session,
                    job,
                    "日更汇总",
                    payload={
                        "trade_date": target.isoformat(),
                        "total_items": job.total_items,
                        "success_items": job.success_items,
                        "failed_items": job.failed_items,
                        "skipped_items": job.skipped_items,
                        "inserted_rows": job.inserted_rows,
                        "updated_rows": job.updated_rows,
                        "status": job.status,
                    },
                )
                session.commit()
                _echo_job_summary(job)
    finally:
        client.logout()
        session.close()


if __name__ == "__main__":
    app()
