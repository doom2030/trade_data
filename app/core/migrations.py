from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


@lru_cache
def expected_migration_head() -> str | None:
    root = Path(__file__).resolve().parent.parent.parent
    ini_path = root / "alembic.ini"
    if not ini_path.exists():
        return None
    config = Config(str(ini_path))
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()
