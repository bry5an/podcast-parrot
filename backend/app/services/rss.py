import re
from datetime import datetime

import feedparser

RSS_URL_PATTERN = re.compile(r"^(https?://|feed://)", re.IGNORECASE)
RSS_EXTENSION_PATTERN = re.compile(r"\.(xml|rss)(\?|$)", re.IGNORECASE)


def looks_like_rss_url(value: str) -> bool:
    value = value.strip()
    return bool(RSS_URL_PATTERN.match(value) or RSS_EXTENSION_PATTERN.search(value))


class FeedFetchError(Exception):
    pass


def fetch_podcast_metadata(rss_url: str) -> dict:
    parsed = feedparser.parse(rss_url)
    if not parsed.entries and parsed.bozo:
        raise FeedFetchError(f"Could not parse feed at {rss_url}")

    feed = parsed.feed
    image = feed.get("image", {}).get("href") if feed.get("image") else None
    language = (feed.get("language") or "en")[:2].lower()
    description = (feed.get("subtitle") or feed.get("description") or "").strip()

    return {
        "title": feed.get("title") or rss_url,
        "description": description,
        "artwork_url": image,
        "language": language,
    }


def _parse_duration(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if ":" in value:
        parts = value.split(":")
        try:
            numbers = [int(p) for p in parts]
        except ValueError:
            return None
        seconds = 0
        for n in numbers:
            seconds = seconds * 60 + n
        return seconds
    try:
        return int(float(value))
    except ValueError:
        return None


def _transcript_url(entry: dict) -> str | None:
    transcript = entry.get("podcast_transcript")
    if isinstance(transcript, list):
        transcript = transcript[0] if transcript else None
    return transcript.get("url") if isinstance(transcript, dict) else None


def fetch_episodes(rss_url: str) -> list[dict]:
    parsed = feedparser.parse(rss_url)
    if not parsed.entries and parsed.bozo:
        raise FeedFetchError(f"Could not parse feed at {rss_url}")

    episodes = []
    for entry in parsed.entries:
        enclosures = entry.get("enclosures") or []
        audio = next((e for e in enclosures if (e.get("type") or "").startswith("audio")), None)
        audio = audio or (enclosures[0] if enclosures else None)
        if not audio or not audio.get("href"):
            continue

        pub_date = None
        if entry.get("published_parsed"):
            pub_date = datetime(*entry.published_parsed[:6])

        guid = entry.get("id") or audio["href"]

        episodes.append(
            {
                "guid": guid,
                "title": entry.get("title") or guid,
                "pub_date": pub_date,
                "duration_seconds": _parse_duration(entry.get("itunes_duration")),
                "audio_url": audio["href"],
                "transcript_source_url": _transcript_url(entry),
            }
        )
    return episodes
