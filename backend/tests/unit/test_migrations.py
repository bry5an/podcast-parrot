import sqlite3

import pytest
from sqlmodel import SQLModel, create_engine

from app import migrations


def _engine_for(db_path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


def _user_version(db_path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def test_fresh_database_is_created_and_stamped_at_current_version(tmp_path):
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)

    migrations.run(db_path, engine)

    assert db_path.exists()
    assert _user_version(db_path) == migrations.CURRENT_VERSION


def test_pre_migration_database_is_backed_up_and_stamped(tmp_path):
    # A database created before this runner existed already has every current
    # table (no schema has changed yet) but user_version 0.
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    SQLModel.metadata.create_all(engine)
    assert _user_version(db_path) == 0

    migrations.run(db_path, engine)

    assert _user_version(db_path) == migrations.CURRENT_VERSION
    assert [p.name for p in tmp_path.glob("*.bak-*")] == ["kotoba.db.bak-0"]


def test_up_to_date_database_is_left_untouched(tmp_path):
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    migrations.run(db_path, engine)
    mtime_before = db_path.stat().st_mtime_ns

    migrations.run(db_path, engine)

    assert db_path.stat().st_mtime_ns == mtime_before
    assert list(tmp_path.glob("*.bak-*")) == []


def test_newer_schema_version_refuses_to_start(tmp_path):
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    migrations.run(db_path, engine)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute(f"PRAGMA user_version = {migrations.CURRENT_VERSION + 1}")
    conn.close()

    with pytest.raises(migrations.SchemaTooNewError):
        migrations.run(db_path, engine)


def test_pending_migration_is_applied_exactly_once_and_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    migrations.run(db_path, engine)  # start at version 1

    calls = []

    def add_widget_column(conn: sqlite3.Connection) -> None:
        calls.append(1)
        conn.execute("ALTER TABLE profile ADD COLUMN widget TEXT")

    monkeypatch.setattr(migrations, "CURRENT_VERSION", 2)
    monkeypatch.setattr(migrations, "MIGRATIONS", {2: add_widget_column})

    migrations.run(db_path, engine)

    assert calls == [1]
    assert _user_version(db_path) == 2
    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(profile)")}
    conn.close()
    assert "widget" in columns
    backups = list(tmp_path.glob("*.bak-*"))
    assert [p.name for p in backups] == ["kotoba.db.bak-1"]

    migrations.run(db_path, engine)  # re-run against the now-current database

    assert calls == [1]  # not re-applied
    assert [p.name for p in tmp_path.glob("*.bak-*")] == ["kotoba.db.bak-1"]  # no new backup taken


def test_failed_migration_step_rolls_back_and_leaves_version_unchanged(tmp_path, monkeypatch):
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    migrations.run(db_path, engine)

    def broken_step(conn: sqlite3.Connection) -> None:
        conn.execute("ALTER TABLE profile ADD COLUMN widget TEXT")
        raise RuntimeError("boom")

    monkeypatch.setattr(migrations, "CURRENT_VERSION", 2)
    monkeypatch.setattr(migrations, "MIGRATIONS", {2: broken_step})

    with pytest.raises(RuntimeError):
        migrations.run(db_path, engine)

    assert _user_version(db_path) == 1
    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(profile)")}
    conn.close()
    assert "widget" not in columns
