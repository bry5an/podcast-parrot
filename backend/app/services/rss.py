import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import httpx
from lxml import etree

RSS_URL_PATTERN = re.compile(r"^(https?://|feed://)", re.IGNORECASE)
RSS_EXTENSION_PATTERN = re.compile(r"\.(xml|rss)(\?|$)", re.IGNORECASE)

PODCAST_NAMESPACE = "https://podcastindex.org/namespace/1.0"
TIMED_TRANSCRIPT_FORMATS = {"srt", "vtt", "json"}


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


def _transcript_candidates_by_item(raw: bytes) -> list[list[dict]]:
    # feedparser doesn't reliably surface the non-standard podcast:transcript
    # tag (and can't carry multiple candidates per item), so we walk the raw
    # XML ourselves, in document order, to line up with feedparser's entries.
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError:
        return []

    all_candidates = []
    for item in root.findall(".//item"):
        candidates = []
        for el in item.findall(f"{{{PODCAST_NAMESPACE}}}transcript"):
            url = el.get("url")
            if not url:
                continue
            candidates.append({"url": url, "type": el.get("type"), "language": el.get("language")})
        all_candidates.append(candidates)
    return all_candidates


def classify_transcript_format(type_attr: str | None, url: str) -> str:
    type_attr = (type_attr or "").lower()
    ext = Path(urlparse(url).path).suffix.lower()
    if "srt" in type_attr or ext == ".srt":
        return "srt"
    if "vtt" in type_attr or ext == ".vtt":
        return "vtt"
    if "json" in type_attr or ext == ".json":
        return "json"
    if "html" in type_attr or ext in (".html", ".htm"):
        return "html"
    if "text" in type_attr or ext == ".txt":
        return "text"
    return "unknown"


def select_transcript_candidate(candidates: list[dict]) -> dict | None:
    """Pick the best podcast:transcript candidate, preferring timed formats
    (SRT/VTT/Podcasting-2.0 JSON) over untimed plain text/HTML."""
    classified = [{**c, "format": classify_transcript_format(c.get("type"), c["url"])} for c in candidates]
    timed = [c for c in classified if c["format"] in TIMED_TRANSCRIPT_FORMATS]
    if timed:
        return timed[0]
    return classified[0] if classified else None


def fetch_episodes(rss_url: str) -> list[dict]:
    try:
        response = httpx.get(rss_url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FeedFetchError(f"Could not fetch feed at {rss_url}") from exc

    raw = response.content
    parsed = feedparser.parse(raw)
    if not parsed.entries and parsed.bozo:
        raise FeedFetchError(f"Could not parse feed at {rss_url}")

    transcript_candidates = _transcript_candidates_by_item(raw)

    episodes = []
    for i, entry in enumerate(parsed.entries):
        enclosures = entry.get("enclosures") or []
        audio = next((e for e in enclosures if (e.get("type") or "").startswith("audio")), None)
        audio = audio or (enclosures[0] if enclosures else None)
        if not audio or not audio.get("href"):
            continue

        pub_date = None
        if entry.get("published_parsed"):
            pub_date = datetime(*entry.published_parsed[:6])

        guid = entry.get("id") or audio["href"]

        candidate = select_transcript_candidate(transcript_candidates[i] if i < len(transcript_candidates) else [])

        episodes.append(
            {
                "guid": guid,
                "title": entry.get("title") or guid,
                "pub_date": pub_date,
                "duration_seconds": _parse_duration(entry.get("itunes_duration")),
                "audio_url": audio["href"],
                "transcript_source_url": candidate["url"] if candidate else None,
                "transcript_source_type": candidate.get("type") if candidate else None,
                "transcript_source_language": candidate.get("language") if candidate else None,
                "transcript_source_format": candidate["format"] if candidate else None,
            }
        )
    return episodes
