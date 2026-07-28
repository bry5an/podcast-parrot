import json

from sqlmodel import Session, SQLModel, create_engine, select

from app import paths
from app.models import Podcast, PodcastSource

DIRECTORY_SEED_PATH = paths.resource_dir() / "backend" / "app" / "directory_seed.json"

DATABASE_URL = f"sqlite:///{paths.data_dir() / 'kotoba.db'}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    paths.data_dir().mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
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
