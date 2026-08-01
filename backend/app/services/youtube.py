import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
import yt_dlp

from app.services.transcript_parsers import Cue, parse_vtt

PLAYLIST_URL_PATTERN = re.compile(r"^https?://(www\.)?youtube\.com/playlist\?.*\blist=", re.IGNORECASE)

# Default learning-direction language for a newly added YouTube podcast:
# playlists expose no reliable spoken-language field, and this app is
# overwhelmingly Japanese-learning-focused (see directory_seed.json).
DEFAULT_LANGUAGE = "ja"


def looks_like_youtube_playlist_url(value: str) -> bool:
    return bool(PLAYLIST_URL_PATTERN.match(value.strip()))


class YoutubeFetchError(Exception):
    pass


class YoutubeDownloadError(Exception):
    pass


def _best_thumbnail(info: dict) -> str | None:
    thumbnails = info.get("thumbnails") or []
    if not thumbnails:
        return None
    url = thumbnails[-1].get("url")
    if not url:
        return None
    # yt-dlp's thumbnail URLs carry a signed sqp=/rs= crop token that expires;
    # the same asset is available permanently at the query-stripped URL
    # (e.g. https://i.ytimg.com/vi/<id>/hqdefault.jpg), so strip it before
    # persisting — otherwise the stored artwork_url goes dead after the token
    # expires (#104).
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def fetch_playlist_metadata(playlist_url: str) -> dict:
    try:
        with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise YoutubeFetchError(f"Could not read playlist at {playlist_url}") from exc

    return {
        "title": info.get("title") or playlist_url,
        "description": (info.get("description") or "").strip(),
        "artwork_url": _best_thumbnail(info),
        "language": DEFAULT_LANGUAGE,
    }


def fetch_playlist_episodes(playlist_url: str) -> list[dict]:
    try:
        with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise YoutubeFetchError(f"Could not read playlist at {playlist_url}") from exc

    episodes = []
    for entry in info.get("entries") or []:
        video_id = entry.get("id")
        if not video_id:
            continue
        episodes.append(
            {
                "guid": video_id,
                "title": entry.get("title") or video_id,
                "pub_date": None,
                "duration_seconds": int(entry["duration"]) if entry.get("duration") else None,
                "audio_url": f"https://www.youtube.com/watch?v={video_id}",
                "transcript_source_url": None,
                "transcript_source_type": None,
                "transcript_source_language": None,
                "transcript_source_format": None,
            }
        )
    return episodes


def fetch_manual_captions(video_url: str, language: str) -> list[Cue] | None:
    """Manual/hand-written captions only — YouTube's own auto-generated
    captions are deliberately ignored here so this app's whisper ASR fallback
    is used instead, per issue #85."""
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise YoutubeFetchError(f"Could not read video at {video_url}") from exc

    tracks = (info.get("subtitles") or {}).get(language)
    if not tracks:
        return None

    vtt_track = next((t for t in tracks if t.get("ext") == "vtt"), None)
    if not vtt_track or not vtt_track.get("url"):
        return None

    try:
        response = httpx.get(vtt_track["url"], timeout=30.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    cues = parse_vtt(response.text)
    return cues or None


def download_audio(video_url: str, dest_dir: Path, episode_id: int) -> Path:
    outtmpl = str(dest_dir / f"{episode_id}.%(ext)s")
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": outtmpl,
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            return Path(ydl.prepare_filename(info))
    except yt_dlp.utils.DownloadError as exc:
        raise YoutubeDownloadError(f"Could not download audio for {video_url}") from exc
