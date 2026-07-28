import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app import paths
from app.services import whisper_models
from app.services.transcript_parsers import Cue

_SENTENCE_TERMINATOR_RE = re.compile(r"[。！？.!?]")
_SPECIAL_TOKEN_RE = re.compile(r"^\[_.+\]$")

_AFCONVERT_BIN = "/usr/bin/afconvert"
_VAD_MODEL_PATH = paths.resource_dir() / "backend" / "app" / "ggml-silero-v5.1.2.bin"

# Neither subprocess call had a timeout, so a stuck decode/inference (#57 saw
# whisper-cli's normal "trying to decode with miniaudio" step never return)
# blocked the background task forever with no way to recover. afconvert
# should finish in low single-digit seconds even for a multi-hour episode;
# whisper-cli's model inference is the slow step and needs enough headroom
# for a full-length episode on CPU-only hardware without a GPU/Metal backend.
_AFCONVERT_TIMEOUT_SECONDS = 120
_WHISPER_CLI_TIMEOUT_SECONDS = 1800


class TranscriptionError(Exception):
    """Base class for ASR failures, distinct from unrelated exceptions."""


class WhisperModelNotFoundError(TranscriptionError):
    """Raised when the configured whisper.cpp model file does not exist on disk."""


@dataclass
class _Word:
    word: str
    start: float
    end: float


@dataclass
class _Segment:
    start: float
    end: float
    text: str
    words: list[_Word]


def _whisper_cli_path() -> Path:
    override = os.environ.get("KOTOBA_WHISPER_BIN")
    if override:
        return Path(override).expanduser().resolve()
    return paths.resource_dir() / "backend" / "bin" / "whisper-cli"


def _model_path() -> Path:
    override = os.environ.get("KOTOBA_WHISPER_MODEL")
    if override:
        return Path(override).expanduser().resolve()
    return whisper_models.active_model_path()


def _segment_to_cues(segment: "_Segment") -> list[Cue]:
    text = segment.text.strip()
    if not text:
        return []

    # Only bother splitting on word timestamps when the segment actually
    # spans more than one sentence (a terminator anywhere but the very end).
    spans_multiple_sentences = bool(_SENTENCE_TERMINATOR_RE.search(text.rstrip("。！？.!? ")))
    if not spans_multiple_sentences or not segment.words:
        return [Cue(segment.start, segment.end, text)]

    cues = []
    group = []
    for word in segment.words:
        group.append(word)
        if _SENTENCE_TERMINATOR_RE.search(word.word):
            sentence_text = "".join(w.word for w in group).strip()
            if sentence_text:
                cues.append(Cue(group[0].start, group[-1].end, sentence_text))
            group = []
    if group:
        sentence_text = "".join(w.word for w in group).strip()
        if sentence_text:
            cues.append(Cue(group[0].start, group[-1].end, sentence_text))

    return cues if cues else [Cue(segment.start, segment.end, text)]


def _decode_to_wav(audio_path: str, wav_path: str) -> None:
    command = [_AFCONVERT_BIN, "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", audio_path, wav_path]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_AFCONVERT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = (exc.stderr or "").strip()
        raise TranscriptionError(
            f"afconvert timed out after {_AFCONVERT_TIMEOUT_SECONDS}s" + (f": {stderr}" if stderr else "")
        ) from None
    if result.returncode != 0:
        raise TranscriptionError(f"afconvert failed ({result.returncode}): {result.stderr.strip()}")


def _run_whisper_cli(wav_path: str, language: str | None, output_prefix: str) -> None:
    model_path = _model_path()
    if not model_path.is_file():
        raise WhisperModelNotFoundError(f"whisper.cpp model not found at {model_path}")

    command = [
        str(_whisper_cli_path()),
        "-m",
        str(model_path),
        "-f",
        wav_path,
        "-l",
        language or "auto",
        "--vad",
        "-vm",
        str(_VAD_MODEL_PATH),
        "-oj",
        "-ojf",
        "-of",
        output_prefix,
        "-np",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_WHISPER_CLI_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = (exc.stderr or "").strip()
        raise TranscriptionError(
            f"whisper-cli timed out after {_WHISPER_CLI_TIMEOUT_SECONDS}s" + (f": {stderr}" if stderr else "")
        ) from None
    if result.returncode != 0:
        raise TranscriptionError(f"whisper-cli failed ({result.returncode}): {result.stderr.strip()}")


def _parse_whisper_json(json_path: str) -> tuple[list[_Segment], str]:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    language = data.get("result", {}).get("language", "")

    segments = []
    for item in data.get("transcription", []):
        words = []
        for token in item.get("tokens", []):
            token_text = token["text"]
            if _SPECIAL_TOKEN_RE.match(token_text.strip()):
                continue
            words.append(
                _Word(
                    word=token_text,
                    start=token["offsets"]["from"] / 1000.0,
                    end=token["offsets"]["to"] / 1000.0,
                )
            )
        segments.append(
            _Segment(
                start=item["offsets"]["from"] / 1000.0,
                end=item["offsets"]["to"] / 1000.0,
                text=item["text"],
                words=words,
            )
        )
    return segments, language


def transcribe_audio(audio_path: str, language: str | None = None) -> tuple[list[Cue], str]:
    """Run whisper.cpp over a local audio file, returning ordered Cues
    (segment-level, split further on sentence-ending punctuation using
    word-level timestamps) plus the detected/used language code."""
    tmp_dir = tempfile.mkdtemp(prefix="kotoba-asr-")
    wav_path = os.path.join(tmp_dir, "audio.wav")
    output_prefix = os.path.join(tmp_dir, "result")
    try:
        _decode_to_wav(audio_path, wav_path)
        _run_whisper_cli(wav_path, language, output_prefix)
        segments, detected_language = _parse_whisper_json(output_prefix + ".json")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    cues = []
    for segment in segments:
        cues.extend(_segment_to_cues(segment))
    return cues, detected_language
