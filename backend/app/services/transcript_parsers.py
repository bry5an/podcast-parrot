import json
import re
from typing import NamedTuple

_TAG_RE = re.compile(r"<[^>]+>")
_SRT_TIME_RE = re.compile(r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})")
_VTT_TIME_RE = re.compile(
    r"((?:\d{2}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*((?:\d{2}:)?\d{2}:\d{2}[.,]\d{3})"
)


class Cue(NamedTuple):
    start_time: float
    end_time: float
    text: str


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def _srt_timestamp_to_seconds(ts: str) -> float:
    hms, _, ms = ts.strip().replace(",", ".").partition(".")
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s) + (int(ms) / 1000 if ms else 0.0)


def _vtt_timestamp_to_seconds(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
    else:
        h, (m, s) = "0", parts
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_srt(content: str) -> list[Cue]:
    cues = []
    for block in re.split(r"\r?\n\r?\n+", content.strip()):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        start_idx = 1 if lines[0].strip().isdigit() else 0
        if start_idx >= len(lines):
            continue
        match = _SRT_TIME_RE.search(lines[start_idx])
        if not match:
            continue
        text = _strip_tags(" ".join(lines[start_idx + 1 :]))
        if text:
            cues.append(
                Cue(
                    _srt_timestamp_to_seconds(match.group(1)),
                    _srt_timestamp_to_seconds(match.group(2)),
                    text,
                )
            )
    return cues


def parse_vtt(content: str) -> list[Cue]:
    cues = []
    for block in re.split(r"\r?\n\r?\n+", content.strip()):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_idx = next((i for i in (0, 1) if i < len(lines) and "-->" in lines[i]), None)
        if time_idx is None:
            continue
        match = _VTT_TIME_RE.search(lines[time_idx])
        if not match:
            continue
        text = _strip_tags(" ".join(lines[time_idx + 1 :]))
        if text:
            cues.append(
                Cue(
                    _vtt_timestamp_to_seconds(match.group(1)),
                    _vtt_timestamp_to_seconds(match.group(2)),
                    text,
                )
            )
    return cues


def parse_json_transcript(content: str) -> list[Cue]:
    data = json.loads(content)
    cues = []
    for segment in data.get("segments") or []:
        start, end = segment.get("startTime"), segment.get("endTime")
        text = (segment.get("body") or "").strip()
        if start is None or end is None or not text:
            continue
        cues.append(Cue(float(start), float(end), text))
    return cues
