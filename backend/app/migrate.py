"""Apply Alembic migrations programmatically (used on API and worker startup)."""

import threading

from alembic import command
from alembic.config import Config

from app.config import BACKEND_DIR

_lock = threading.Lock()


def upgrade_db() -> None:
    with _lock:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(cfg, "head")
