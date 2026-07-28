import json
import os

import pytest

from app.services.transcript_parsers import Cue
from app.services.transcription import (
    TranscriptionError,
    WhisperModelNotFoundError,
    _Segment,
    _segment_to_cues,
    _Word,
    transcribe_audio,
)


def _word(text, start, end):
    return _Word(word=text, start=start, end=end)


# --- _segment_to_cues: engine-independent, exercised directly ---------


def test_single_sentence_segment_returns_one_cue():
    segment = _Segment(start=0.0, end=1.0, text=" Hello there.", words=[])
    assert _segment_to_cues(segment) == [Cue(0.0, 1.0, "Hello there.")]


def test_empty_text_returns_no_cues():
    segment = _Segment(start=0.0, end=1.0, text="   ", words=[])
    assert _segment_to_cues(segment) == []


def test_trailing_terminator_only_is_not_split():
    words = [_word(" Just", 0.0, 0.2), _word(" one.", 0.2, 0.5)]
    segment = _Segment(start=0.0, end=0.5, text=" Just one.", words=words)
    assert _segment_to_cues(segment) == [Cue(0.0, 0.5, "Just one.")]


def test_multi_sentence_segment_splits_on_word_timestamps():
    words = [
        _word(" This", 0.0, 0.3),
        _word(" is", 0.3, 0.5),
        _word(" one.", 0.5, 1.0),
        _word(" This", 1.0, 1.3),
        _word(" is", 1.3, 1.5),
        _word(" two!", 1.5, 2.0),
    ]
    segment = _Segment(start=0.0, end=2.0, text=" This is one. This is two!", words=words)
    assert _segment_to_cues(segment) == [
        Cue(0.0, 1.0, "This is one."),
        Cue(1.0, 2.0, "This is two!"),
    ]


def test_multi_sentence_segment_without_words_falls_back_to_whole_segment():
    segment = _Segment(start=0.0, end=2.0, text=" This is one. This is two!", words=[])
    assert _segment_to_cues(segment) == [Cue(0.0, 2.0, "This is one. This is two!")]


def test_japanese_terminators_split_sentences():
    words = [
        _word("こんにちは", 0.0, 0.5),
        _word("。", 0.5, 0.6),
        _word("元気", 0.6, 1.0),
        _word("ですか", 1.0, 1.3),
        _word("?", 1.3, 1.4),
    ]
    segment = _Segment(start=0.0, end=1.4, text="こんにちは。元気ですか?", words=words)
    assert _segment_to_cues(segment) == [
        Cue(0.0, 0.6, "こんにちは。"),
        Cue(0.6, 1.4, "元気ですか?"),
    ]


# --- transcribe_audio: subprocess boundary is stubbed ------------------


class _FakeResult:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


def _whisper_json_fixture():
    return {
        "result": {"language": "ja"},
        "transcription": [
            {
                "offsets": {"from": 0, "to": 2000},
                "text": " こんにちは。",
                "tokens": [
                    {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}},
                    {"text": "こんにちは", "offsets": {"from": 0, "to": 1500}},
                    {"text": "。", "offsets": {"from": 1500, "to": 2000}},
                    {"text": "[_TT_100]", "offsets": {"from": 2000, "to": 2000}},
                ],
            }
        ],
    }


def _make_fake_run(calls, json_payload, whisper_returncode=0, whisper_stderr=""):
    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0] == "/usr/bin/afconvert":
            return _FakeResult(returncode=0)
        if whisper_returncode != 0:
            return _FakeResult(returncode=whisper_returncode, stderr=whisper_stderr)
        prefix = command[command.index("-of") + 1]
        with open(prefix + ".json", "w", encoding="utf-8") as f:
            json.dump(json_payload, f)
        return _FakeResult(returncode=0)

    return fake_run


def _stub_model(monkeypatch, tmp_path, exists=True):
    model_path = tmp_path / "model.bin"
    if exists:
        model_path.touch()
    monkeypatch.setenv("KOTOBA_WHISPER_BIN", "/fake/whisper-cli")
    monkeypatch.setenv("KOTOBA_WHISPER_MODEL", str(model_path))


def test_transcribe_audio_happy_path(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        "app.services.transcription.subprocess.run", _make_fake_run(calls, _whisper_json_fixture())
    )

    cues, language = transcribe_audio("/fake/input.mp3", language="ja")

    assert language == "ja"
    assert cues == [Cue(0.0, 2.0, "こんにちは。")]
    assert calls[0][0] == "/usr/bin/afconvert"
    assert calls[0][-2] == "/fake/input.mp3"
    assert calls[1][0] == "/fake/whisper-cli"
    assert calls[1][calls[1].index("-l") + 1] == "ja"


def test_transcribe_audio_language_none_passes_auto(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        "app.services.transcription.subprocess.run", _make_fake_run(calls, _whisper_json_fixture())
    )

    transcribe_audio("/fake/input.mp3")

    whisper_call = calls[1]
    assert whisper_call[whisper_call.index("-l") + 1] == "auto"


def test_special_tokens_are_filtered_from_words(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    payload = {
        "result": {"language": "en"},
        "transcription": [
            {
                "offsets": {"from": 0, "to": 4000},
                "text": " One. Two!",
                "tokens": [
                    {"text": "[_BEG_]", "offsets": {"from": 0, "to": 0}},
                    {"text": " One.", "offsets": {"from": 0, "to": 2000}},
                    {"text": " Two!", "offsets": {"from": 2000, "to": 4000}},
                    {"text": "[_TT_400]", "offsets": {"from": 4000, "to": 4000}},
                ],
            }
        ],
    }
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_run(calls, payload))

    cues, _ = transcribe_audio("/fake/input.mp3", language="en")

    assert cues == [Cue(0.0, 2.0, "One."), Cue(2.0, 4.0, "Two!")]


def test_missing_model_raises_distinct_error_without_shelling_to_whisper_cli(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path, exists=False)
    calls = []
    monkeypatch.setattr(
        "app.services.transcription.subprocess.run", _make_fake_run(calls, _whisper_json_fixture())
    )

    with pytest.raises(WhisperModelNotFoundError):
        transcribe_audio("/fake/input.mp3")

    assert len(calls) == 1  # afconvert ran; whisper-cli was never invoked


def test_afconvert_failure_raises_transcription_error(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.transcription.subprocess.run",
        lambda command, **kwargs: _FakeResult(returncode=1, stderr="boom"),
    )

    with pytest.raises(TranscriptionError):
        transcribe_audio("/fake/input.mp3")


def test_whisper_cli_failure_raises_transcription_error(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        "app.services.transcription.subprocess.run",
        _make_fake_run(calls, _whisper_json_fixture(), whisper_returncode=1, whisper_stderr="exploded"),
    )

    with pytest.raises(TranscriptionError):
        transcribe_audio("/fake/input.mp3")


def test_temp_directory_cleaned_up_after_success(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        "app.services.transcription.subprocess.run", _make_fake_run(calls, _whisper_json_fixture())
    )

    transcribe_audio("/fake/input.mp3", language="ja")

    wav_path = calls[0][-1]
    assert not os.path.isdir(os.path.dirname(wav_path))


def test_temp_directory_cleaned_up_after_failure(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        "app.services.transcription.subprocess.run",
        _make_fake_run(calls, _whisper_json_fixture(), whisper_returncode=1, whisper_stderr="exploded"),
    )

    with pytest.raises(TranscriptionError):
        transcribe_audio("/fake/input.mp3")

    wav_path = calls[0][-1]
    assert not os.path.isdir(os.path.dirname(wav_path))
