from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.models import Episode, Podcast
from app.services.rss import FeedFetchError, fetch_episodes

POLL_INTERVAL = timedelta(minutes=15)


def sync_episodes(session: Session, podcast: Podcast) -> None:
    if podcast.last_polled_at and datetime.utcnow() - podcast.last_polled_at < POLL_INTERVAL:
        return

    try:
        fetched = fetch_episodes(podcast.rss_url)
    except FeedFetchError:
        return

    existing = {
        e.guid: e
        for e in session.exec(select(Episode).where(Episode.podcast_id == podcast.id)).all()
    }
    for data in fetched:
        episode = existing.get(data["guid"])
        if episode:
            episode.title = data["title"]
            episode.pub_date = data["pub_date"]
            episode.duration_seconds = data["duration_seconds"]
            episode.audio_url = data["audio_url"]
            episode.transcript_source_url = data["transcript_source_url"]
            session.add(episode)
        else:
            session.add(Episode(podcast_id=podcast.id, **data))

    podcast.last_polled_at = datetime.utcnow()
    session.add(podcast)
    session.commit()
