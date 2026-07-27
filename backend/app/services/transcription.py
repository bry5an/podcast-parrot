import os
import re
from typing import TYPE_CHECKING

from app.services.transcript_parsers import Cue

if TYPE_CHECKING:
    from faster_whisper.transcribe import Segment

WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

_SENTENCE_TERMINATOR_RE = re.compile(r"[。！？.!?]")

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    return _model


def _segment_to_cues(segment: "Segment") -> list[Cue]:
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


def transcribe_audio(audio_path: str, language: str | None = None) -> tuple[list[Cue], str]:
    """Run faster-whisper over a local audio file, returning ordered Cues
    (segment-level, split further on sentence-ending punctuation using
    word-level timestamps) plus the detected/used language code."""
    model = _get_model()
    segments, info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        vad_filter=True,
    )

    cues = []
    for segment in segments:
        cues.extend(_segment_to_cues(segment))
    return cues, info.language
