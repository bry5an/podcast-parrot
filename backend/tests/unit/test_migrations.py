import sqlite3

import pytest
from sqlmodel import SQLModel, create_engine

from app import migrations
from app.models import SavedSentence  # noqa: F401 — ensures the table is registered on SQLModel.metadata


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
    # A database created before this runner existed already has every table
    # that existed at version 1 (no schema had changed yet) but user_version 0.
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    v1_tables = [t for name, t in SQLModel.metadata.tables.items() if name not in ("savedsentence", "appsettings")]
    SQLModel.metadata.create_all(engine, tables=v1_tables)
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


def test_v1_database_gains_a_working_savedsentence_table(tmp_path):
    # Simulates a real pre-existing install: every v1 table but savedsentence,
    # stamped at version 1 — exactly what a database created before this
    # migration shipped looks like.
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    v1_tables = [t for name, t in SQLModel.metadata.tables.items() if name not in ("savedsentence", "appsettings")]
    SQLModel.metadata.create_all(engine, tables=v1_tables)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("PRAGMA user_version = 1")
    conn.close()

    migrations.run(db_path, engine)

    assert _user_version(db_path) == migrations.CURRENT_VERSION
    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
    assert "savedsentence" in tables
    columns = {row[1] for row in conn.execute("PRAGMA table_info(savedsentence)")}
    assert columns == {
        "id",
        "profile_id",
        "episode_id",
        "name",
        "start_sentence_id",
        "end_sentence_id",
        "created_at",
    }
    # The table is actually usable, not just present.
    conn.execute(
        "INSERT INTO profile (name, palette_index, direction, show_furigana, created_at) "
        "VALUES ('Kenji', 0, 'en_ja', 1, '2024-01-01')"
    )
    conn.execute(
        "INSERT INTO podcast (rss_url, kind, title, description, language, source) "
        "VALUES ('https://x', 'rss', 'Show', '', 'ja', 'user_added')"
    )
    conn.execute(
        "INSERT INTO episode (podcast_id, guid, title, audio_url, download_status, transcript_status) "
        "VALUES (1, 'g', 'Ep', 'https://x/a.mp3', 'idle', 'none')"
    )
    conn.execute(
        "INSERT INTO transcript (episode_id, language, source, created_at) "
        "VALUES (1, 'ja', 'published', '2024-01-01')"
    )
    conn.execute(
        "INSERT INTO sentence (transcript_id, \"index\", start_time, end_time, text, segments) "
        "VALUES (1, 0, 0, 1, 'hi', '[]')"
    )
    conn.execute(
        "INSERT INTO savedsentence (profile_id, episode_id, name, start_sentence_id, end_sentence_id, created_at) "
        "VALUES (1, 1, 'clip', 1, 1, '2024-01-01')"
    )
    conn.commit()
    assert conn.execute("SELECT name FROM savedsentence").fetchone() == ("clip",)
    conn.close()


def test_fresh_database_includes_savedsentence_table(tmp_path):
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)

    migrations.run(db_path, engine)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
    conn.close()
    assert "savedsentence" in tables


def test_pending_migration_is_applied_exactly_once_and_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    monkeypatch.setattr(migrations, "CURRENT_VERSION", 1)
    monkeypatch.setattr(migrations, "MIGRATIONS", {})
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


def test_v2_podcast_table_gains_kind_and_youtube_columns(tmp_path):
    # Simulates a real pre-#85 install: the exact podcast schema that shipped
    # before youtube_playlist_url/kind existed (rss_url required and unique),
    # with one real row in it, stamped at version 2.
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    # Stamped at version 2, so savedsentence (added by the version-2 step) already
    # exists; only podcast (rebuilt at version 3) and appsettings (version 4) don't.
    other_v2_tables = [t for name, t in SQLModel.metadata.tables.items() if name not in ("podcast", "appsettings")]
    SQLModel.metadata.create_all(engine, tables=other_v2_tables)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute(
        """
        CREATE TABLE podcast (
            id INTEGER NOT NULL,
            rss_url VARCHAR NOT NULL,
            title VARCHAR NOT NULL,
            description VARCHAR NOT NULL,
            artwork_url VARCHAR,
            language VARCHAR NOT NULL,
            level_tag VARCHAR,
            source VARCHAR(10) NOT NULL,
            last_polled_at DATETIME,
            PRIMARY KEY (id)
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX ix_podcast_rss_url ON podcast (rss_url)")
    conn.execute(
        "INSERT INTO podcast (id, rss_url, title, description, language, source) "
        "VALUES (1, 'https://example.com/feed.xml', 'Nihongo News', '', 'ja', 'user_added')"
    )
    conn.execute("PRAGMA user_version = 2")
    conn.close()

    migrations.run(db_path, engine)

    assert _user_version(db_path) == migrations.CURRENT_VERSION
    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(podcast)")}
    assert {"rss_url", "youtube_playlist_url", "kind"} <= columns

    row = conn.execute("SELECT id, rss_url, youtube_playlist_url, kind, title FROM podcast").fetchone()
    assert row == (1, "https://example.com/feed.xml", None, "rss", "Nihongo News")

    # A new YouTube-sourced row (no rss_url) is now insertable...
    conn.execute(
        "INSERT INTO podcast (rss_url, youtube_playlist_url, kind, title, description, language, source) "
        "VALUES (NULL, 'https://www.youtube.com/playlist?list=abc', 'youtube', 'Show', '', 'ja', 'user_added')"
    )
    conn.commit()
    # ...and rss_url uniqueness (ignoring the now-many NULLs) is still enforced.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO podcast (rss_url, kind, title, description, language, source) "
            "VALUES ('https://example.com/feed.xml', 'rss', 'Dupe', '', 'ja', 'user_added')"
        )
    conn.close()


def test_stamped_current_version_with_missing_table_fails_loudly(tmp_path):
    # Reproduces the #96/#97 incident: user_version says the schema is current,
    # but a table that version implies (appsettings) doesn't actually exist —
    # e.g. because CURRENT_VERSION was bumped before its MIGRATIONS step landed.
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    migrations.run(db_path, engine)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.execute("DROP TABLE appsettings")
    conn.close()

    with pytest.raises(migrations.SchemaMismatchError):
        migrations.run(db_path, engine)


def test_failed_migration_step_rolls_back_and_leaves_version_unchanged(tmp_path, monkeypatch):
    db_path = tmp_path / "kotoba.db"
    engine = _engine_for(db_path)
    monkeypatch.setattr(migrations, "CURRENT_VERSION", 1)
    monkeypatch.setattr(migrations, "MIGRATIONS", {})
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
