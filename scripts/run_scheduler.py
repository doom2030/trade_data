import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import typer

from app.core.logging import setup_logging
from collector.scheduler import run_scheduler_loop

app = typer.Typer()


@app.command()
def main():
    """Run the in-container schedule loop (daily update + optional industry sync)."""
    setup_logging()
    run_scheduler_loop()


if __name__ == "__main__":
    app()
