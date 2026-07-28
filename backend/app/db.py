import json

from sqlmodel import Session, create_engine, select

from app import migrations, paths
from app.models import Podcast, PodcastSource

DIRECTORY_SEED_PATH = paths.resource_dir() / "backend" / "app" / "directory_seed.json"

DB_PATH = paths.data_dir() / "kotoba.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    paths.data_dir().mkdir(parents=True, exist_ok=True)
    migrations.run(DB_PATH, engine)
    _seed_directory()


def _seed_directory() -> None:
    entries = json.loads(DIRECTORY_SEED_PATH.read_text())
    with Session(engine) as session:
        existing_urls = set(session.exec(select(Podcast.rss_url)).all())
        for entry in entries:
            if entry["rss_url"] in existing_urls:
                continue
            session.add(Podcast(source=PodcastSource.curated, **entry))
        session.commit()


def get_session():
    with Session(engine) as session:
        yield session
