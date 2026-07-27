import json
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Podcast, PodcastSource

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DIRECTORY_SEED_PATH = Path(__file__).resolve().parent / "directory_seed.json"

DATABASE_URL = f"sqlite:///{DATA_DIR / 'kotoba.db'}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
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
