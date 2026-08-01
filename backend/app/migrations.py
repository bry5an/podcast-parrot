import logging
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import SQLModel

logger = logging.getLogger(__name__)

CURRENT_VERSION = 7

Migration = Callable[[sqlite3.Connection], None]


def _add_saved_sentence_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE savedsentence (
            id INTEGER NOT NULL,
            profile_id INTEGER NOT NULL,
            episode_id INTEGER NOT NULL,
            name VARCHAR NOT NULL,
            start_sentence_id INTEGER NOT NULL,
            end_sentence_id INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(profile_id) REFERENCES profile (id),
            FOREIGN KEY(episode_id) REFERENCES episode (id),
            FOREIGN KEY(start_sentence_id) REFERENCES sentence (id),
            FOREIGN KEY(end_sentence_id) REFERENCES sentence (id)
        )
        """
    )
    conn.execute("CREATE INDEX ix_savedsentence_profile_id ON savedsentence (profile_id)")
    conn.execute("CREATE INDEX ix_savedsentence_episode_id ON savedsentence (episode_id)")
    conn.execute("CREATE INDEX ix_savedsentence_created_at ON savedsentence (created_at)")


def _make_podcast_kind_aware(conn: sqlite3.Connection) -> None:
    # SQLite can't drop a NOT NULL constraint via ALTER TABLE, so rss_url
    # becoming optional (YouTube-sourced podcasts have none) requires a full
    # table rebuild rather than an ADD COLUMN. `id` is copied verbatim so
    # episode.podcast_id foreign keys stay valid.
    conn.execute(
        """
        CREATE TABLE podcast_new (
            id INTEGER NOT NULL,
            rss_url VARCHAR,
            youtube_playlist_url VARCHAR,
            kind VARCHAR(7) NOT NULL,
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
    conn.execute(
        """
        INSERT INTO podcast_new
            (id, rss_url, youtube_playlist_url, kind, title, description, artwork_url,
             language, level_tag, source, last_polled_at)
        SELECT id, rss_url, NULL, 'rss', title, description, artwork_url,
               language, level_tag, source, last_polled_at
        FROM podcast
        """
    )
    conn.execute("DROP TABLE podcast")
    conn.execute("ALTER TABLE podcast_new RENAME TO podcast")
    conn.execute("CREATE UNIQUE INDEX ix_podcast_rss_url ON podcast (rss_url)")
    conn.execute("CREATE UNIQUE INDEX ix_podcast_youtube_playlist_url ON podcast (youtube_playlist_url)")


def _add_app_settings_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE appsettings (
            id INTEGER NOT NULL,
            auto_remove VARCHAR(6) NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    conn.execute("INSERT INTO appsettings (id, auto_remove) VALUES (1, 'never')")


def _add_podcast_local_directory_path(conn: sqlite3.Connection) -> None:
    # Unlike v3's rss_url NOT NULL relaxation, this is a brand-new nullable
    # column, so a plain ADD COLUMN works — no full table rebuild needed.
    conn.execute("ALTER TABLE podcast ADD COLUMN local_directory_path VARCHAR")
    conn.execute("CREATE UNIQUE INDEX ix_podcast_local_directory_path ON podcast (local_directory_path)")


def _add_profile_last_used_at(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE profile ADD COLUMN last_used_at DATETIME")


def _profile_direction_to_learning_language(conn: sqlite3.Connection) -> None:
    # `direction` modeled a fixed native/target language pair (en_ja/ja_en).
    # The app is now native-language-agnostic: profiles just name the
    # language being learned. SQLite can't drop/retype a column via plain
    # ALTER TABLE, so this rebuilds the table like v3's _make_podcast_kind_aware
    # rather than leaving the old column behind as dead data.
    conn.execute(
        """
        CREATE TABLE profile_new (
            id INTEGER NOT NULL,
            name VARCHAR NOT NULL,
            palette_index INTEGER NOT NULL,
            learning_language VARCHAR(5) NOT NULL,
            show_furigana BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL,
            last_used_at DATETIME,
            PRIMARY KEY (id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO profile_new
            (id, name, palette_index, learning_language, show_furigana, created_at, last_used_at)
        SELECT id, name, palette_index,
               CASE direction WHEN 'en_ja' THEN 'ja' WHEN 'ja_en' THEN 'en' ELSE 'ja' END,
               show_furigana, created_at, last_used_at
        FROM profile
        """
    )
    conn.execute("DROP TABLE profile")
    conn.execute("ALTER TABLE profile_new RENAME TO profile")


# Keyed by the version each step migrates *to*. Version 1 is exactly the schema
# `SQLModel.metadata.create_all()` produces, so it has no step here — both a
# brand-new database and a pre-migration one are simply stamped at that version.
MIGRATIONS: dict[int, Migration] = {
    2: _add_saved_sentence_table,
    3: _make_podcast_kind_aware,
    4: _add_app_settings_table,
    5: _add_podcast_local_directory_path,
    6: _add_profile_last_used_at,
    7: _profile_direction_to_learning_language,
}


class SchemaTooNewError(RuntimeError):
    pass


class SchemaMismatchError(RuntimeError):
    pass


def run(db_path: Path, engine: Engine) -> None:
    if not db_path.exists():
        SQLModel.metadata.create_all(engine)
        conn = sqlite3.connect(db_path, isolation_level=None)
        try:
            conn.execute("INSERT INTO appsettings (id, auto_remove) VALUES (1, 'never')")
        finally:
            conn.close()
        _stamp(db_path, CURRENT_VERSION)
        _verify_schema(db_path)
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
        _verify_schema(db_path)
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
    _verify_schema(db_path)
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


def _verify_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        existing_tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        missing_tables = []
        missing_columns = []
        for table_name, table in SQLModel.metadata.tables.items():
            if table_name not in existing_tables:
                missing_tables.append(table_name)
                continue
            existing_columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")')}
            for column in table.columns:
                if column.name not in existing_columns:
                    missing_columns.append(f"{table_name}.{column.name}")
    finally:
        conn.close()

    if missing_tables or missing_columns:
        raise SchemaMismatchError(
            f"{db_path.name} is stamped at schema version {CURRENT_VERSION}, but its schema doesn't "
            f"match: missing tables {missing_tables}, missing columns {missing_columns}. This usually "
            f"means CURRENT_VERSION was bumped before its migration step landed, or a migration step "
            f"failed in a way that still let the version stamp through. Restore from a "
            f"{db_path.name}.bak-* file or repair the schema by hand."
        )
