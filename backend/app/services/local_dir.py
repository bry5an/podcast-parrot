from datetime import datetime
from pathlib import Path

# Formats afconvert (see services/transcription.py) can decode. Deliberately
# excludes .ogg — Core Audio has no native Ogg Vorbis decoder.
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".aiff", ".caf"}

# Sidecar transcript extensions this app already knows how to parse (see
# transcripts._PARSERS). The extension (without the dot) doubles as the
# transcript_source_type/transcript_source_format value so the existing
# RSS-derived classification in services/episodes.py._apply_transcript_fields
# (which checks membership in rss.TIMED_TRANSCRIPT_FORMATS) picks these up
# with no changes.
TRANSCRIPT_EXTENSIONS = (".srt", ".vtt", ".json")

# Playlists/local folders expose no reliable spoken-language field, and this
# app is overwhelmingly Japanese-learning-focused (see directory_seed.json),
# same rationale as youtube.DEFAULT_LANGUAGE.
DEFAULT_LANGUAGE = "ja"


class LocalDirectoryError(Exception):
    pass


def _audio_files(directory: Path) -> list[Path]:
    try:
        entries = list(directory.iterdir())
    except OSError as exc:
        raise LocalDirectoryError(f"Could not read {directory}: {exc}") from exc
    return sorted(
        (p for p in entries if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS),
        key=lambda p: p.name,
    )


def validate_directory(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.is_dir():
        raise LocalDirectoryError(f"{path} is not a directory")
    if not _audio_files(path):
        raise LocalDirectoryError(f"No audio files found in {path}")
    return path


def fetch_directory_metadata(path: Path) -> dict:
    return {
        "title": path.name,
        "description": "",
        "artwork_url": None,
        "language": DEFAULT_LANGUAGE,
    }


def _find_transcript_sidecar(audio_path: Path) -> Path | None:
    for ext in TRANSCRIPT_EXTENSIONS:
        candidate = audio_path.with_suffix(ext)
        if candidate.is_file():
            return candidate
    return None


def scan_episodes(directory: Path) -> list[dict]:
    episodes = []
    for audio_path in _audio_files(directory):
        sidecar = _find_transcript_sidecar(audio_path)
        transcript_format = sidecar.suffix.lstrip(".") if sidecar else None
        episodes.append(
            {
                "guid": audio_path.name,
                "title": audio_path.stem,
                "pub_date": datetime.fromtimestamp(audio_path.stat().st_mtime),
                "duration_seconds": None,
                "audio_url": str(audio_path),
                "transcript_source_url": str(sidecar) if sidecar else None,
                "transcript_source_type": transcript_format,
                "transcript_source_language": None,
                "transcript_source_format": transcript_format,
            }
        )
    return episodes
