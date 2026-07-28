import logging
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import SQLModel

logger = logging.getLogger(__name__)

CURRENT_VERSION = 1

Migration = Callable[[sqlite3.Connection], None]

# Keyed by the version each step migrates *to*. Version 1 is exactly the schema
# `SQLModel.metadata.create_all()` produces, so it has no step here — both a
# brand-new database and a pre-migration one are simply stamped at that version.
MIGRATIONS: dict[int, Migration] = {}


class SchemaTooNewError(RuntimeError):
    pass


def run(db_path: Path, engine: Engine) -> None:
    if not db_path.exists():
        SQLModel.metadata.create_all(engine)
        _stamp(db_path, CURRENT_VERSION)
        return

    version = _read_version(db_path)
    if version > CURRENT_VERSION:
        raise SchemaTooNewError(
            f"{db_path.name} is at schema version {version}, but this build of the app only "
            f"understands up to version {CURRENT_VERSION}. This usually means an older version of "
            f"the app was installed over a newer one. Reinstall the version that last ran "
            f"successfully, or restore from a {db_path.name}.bak-* file."
        )
    if version == CURRENT_VERSION:
        return

    backup_path = db_path.with_name(f"{db_path.name}.bak-{version}")
    shutil.copy2(db_path, backup_path)
    logger.info("Backed up %s to %s before migrating", db_path.name, backup_path.name)

    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute("BEGIN")
        for target in range(version + 1, CURRENT_VERSION + 1):
            step = MIGRATIONS.get(target)
            if step is not None:
                step(conn)
            conn.execute(f"PRAGMA user_version = {target}")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    logger.info("Migrated %s from version %s to %s", db_path.name, version, CURRENT_VERSION)


def _read_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def _stamp(db_path: Path, version: int) -> None:
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        conn.execute(f"PRAGMA user_version = {version}")
    finally:
        conn.close()
