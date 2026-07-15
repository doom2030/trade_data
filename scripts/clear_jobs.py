"""Clear existing collect jobs and related records."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.core.logging import setup_logging
from app.models import CollectJob, CollectJobItem, CollectJobLog, QualityCheckResult

app = typer.Typer()


@app.command()
def main(
    yes: bool = typer.Option(
        False,
        "--yes",
        help="确认删除任务、任务明细、执行日志和质量检查记录",
    ),
):
    setup_logging()
    session = SessionLocal()
    try:
        counts = {
            "collect_job": session.scalar(select(func.count()).select_from(CollectJob)) or 0,
            "collect_job_item": session.scalar(select(func.count()).select_from(CollectJobItem)) or 0,
            "collect_job_log": session.scalar(select(func.count()).select_from(CollectJobLog)) or 0,
            "quality_check_result": session.scalar(select(func.count()).select_from(QualityCheckResult)) or 0,
        }

        typer.echo("将清理以下记录：")
        for table, count in counts.items():
            typer.echo(f"  {table}: {count}")

        if not yes:
            typer.echo("")
            typer.echo("当前为 dry-run，未删除任何数据。确认删除请加 --yes")
            raise typer.Exit(0)

        session.execute(delete(QualityCheckResult))
        session.execute(delete(CollectJobLog))
        session.execute(delete(CollectJobItem))
        session.execute(delete(CollectJob))
        session.commit()
        typer.echo("任务相关记录已清空")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    app()
