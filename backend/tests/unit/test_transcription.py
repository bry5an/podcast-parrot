import json
import os
import subprocess

import pytest

from app.models import ComputeDevice
from app.services.transcript_parsers import Cue
from app.services.transcription import (
    TranscriptionError,
    WhisperModelNotFoundError,
    _Segment,
    _segment_to_cues,
    _Word,
    get_progress,
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
#
# afconvert still goes through subprocess.run; whisper-cli now goes through
# subprocess.Popen + a background stderr-reading thread (so "-pp"'s
# incremental "progress = NN%" lines can be parsed as they arrive). Each
# boundary is faked separately below.


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


def _make_fake_afconvert_run(calls, returncode=0, stderr="", kwargs_log=None):
    def fake_run(command, **kwargs):
        calls.append(command)
        if kwargs_log is not None:
            kwargs_log.append(kwargs)
        if returncode != 0:
            return _FakeResult(returncode=returncode, stderr=stderr)
        return _FakeResult(returncode=0)

    return fake_run


def _make_fake_afconvert_timeout(kwargs_log=None):
    def fake_run(command, **kwargs):
        if kwargs_log is not None:
            kwargs_log.append(kwargs)
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get("timeout"))

    return fake_run


def _make_fake_popen(
    calls,
    json_payload=None,
    returncode=0,
    stderr_lines=None,
    timeout_on_first_wait=False,
    wait_log=None,
):
    """Stands in for subprocess.Popen against an in-memory stderr line list,
    so _run_whisper_cli's Popen + reader-thread wiring is actually exercised
    without shelling out to a real whisper-cli binary."""
    stderr_lines = list(stderr_lines or [])

    class _FakePopen:
        def __init__(self, command, **kwargs):
            calls.append(command)
            self.args = command
            self.returncode = None
            self.stdout = None
            self.stderr = iter(stderr_lines)
            self._wait_calls = 0
            if json_payload is not None and returncode == 0:
                prefix = command[command.index("-of") + 1]
                with open(prefix + ".json", "w", encoding="utf-8") as f:
                    json.dump(json_payload, f)

        def wait(self, timeout=None):
            if wait_log is not None:
                wait_log.append(timeout)
            self._wait_calls += 1
            if timeout_on_first_wait and self._wait_calls == 1:
                raise subprocess.TimeoutExpired(cmd=self.args, timeout=timeout)
            self.returncode = returncode
            return self.returncode

        def kill(self):
            pass

    return _FakePopen


def _stub_model(monkeypatch, tmp_path, exists=True):
    model_path = tmp_path / "model.bin"
    if exists:
        model_path.touch()
    monkeypatch.setenv("KOTOBA_WHISPER_BIN", "/fake/whisper-cli")
    monkeypatch.setenv("KOTOBA_WHISPER_MODEL", str(model_path))


def test_transcribe_audio_happy_path(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr("app.services.transcription.subprocess.Popen", _make_fake_popen(calls, _whisper_json_fixture()))

    cues, language = transcribe_audio("/fake/input.mp3", language="ja")

    assert language == "ja"
    assert cues == [Cue(0.0, 2.0, "こんにちは。")]
    assert calls[0][0] == "/usr/bin/afconvert"
    assert calls[0][-2] == "/fake/input.mp3"
    assert calls[1][0] == "/fake/whisper-cli"
    assert calls[1][calls[1].index("-l") + 1] == "ja"
    assert "-pp" in calls[1]


def test_transcribe_audio_defaults_to_gpu_and_omits_no_gpu_flag(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr("app.services.transcription.subprocess.Popen", _make_fake_popen(calls, _whisper_json_fixture()))

    transcribe_audio("/fake/input.mp3", language="ja")

    assert "-ng" not in calls[1]


def test_transcribe_audio_cpu_device_passes_no_gpu_flag(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr("app.services.transcription.subprocess.Popen", _make_fake_popen(calls, _whisper_json_fixture()))

    transcribe_audio("/fake/input.mp3", language="ja", compute_device=ComputeDevice.cpu)

    assert "-ng" in calls[1]


def test_transcribe_audio_language_none_passes_auto(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr("app.services.transcription.subprocess.Popen", _make_fake_popen(calls, _whisper_json_fixture()))

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
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr("app.services.transcription.subprocess.Popen", _make_fake_popen(calls, payload))

    cues, _ = transcribe_audio("/fake/input.mp3", language="en")

    assert cues == [Cue(0.0, 2.0, "One."), Cue(2.0, 4.0, "Two!")]


def test_missing_model_raises_distinct_error_without_shelling_to_whisper_cli(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path, exists=False)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr("app.services.transcription.subprocess.Popen", _make_fake_popen(calls, _whisper_json_fixture()))

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
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr(
        "app.services.transcription.subprocess.Popen",
        _make_fake_popen(calls, returncode=1, stderr_lines=["exploded\n"]),
    )

    with pytest.raises(TranscriptionError, match="exploded"):
        transcribe_audio("/fake/input.mp3")


def test_temp_directory_cleaned_up_after_success(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr("app.services.transcription.subprocess.Popen", _make_fake_popen(calls, _whisper_json_fixture()))

    transcribe_audio("/fake/input.mp3", language="ja")

    wav_path = calls[0][-1]
    assert not os.path.isdir(os.path.dirname(wav_path))


def test_temp_directory_cleaned_up_after_failure(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr(
        "app.services.transcription.subprocess.Popen",
        _make_fake_popen(calls, returncode=1, stderr_lines=["exploded\n"]),
    )

    with pytest.raises(TranscriptionError):
        transcribe_audio("/fake/input.mp3")

    wav_path = calls[0][-1]
    assert not os.path.isdir(os.path.dirname(wav_path))


# --- ASR progress reporting (#69) ---------------------------------------


def test_progress_lines_update_get_progress(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr(
        "app.services.transcription.subprocess.Popen",
        _make_fake_popen(
            calls,
            _whisper_json_fixture(),
            stderr_lines=[
                "whisper_print_progress_callback: progress =  16%\n",
                "read_audio_data: trying to decode with miniaudio\n",
                "whisper_print_progress_callback: progress = 100%\n",
            ],
        ),
    )

    try:
        transcribe_audio("/fake/input.mp3", episode_id=42)
        assert get_progress(42) == 100
    finally:
        from app.services.transcription import clear_progress

        clear_progress(42)


def test_transcribe_audio_without_episode_id_does_not_track_progress(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr(
        "app.services.transcription.subprocess.Popen",
        _make_fake_popen(
            calls,
            _whisper_json_fixture(),
            stderr_lines=["whisper_print_progress_callback: progress = 100%\n"],
        ),
    )

    transcribe_audio("/fake/input.mp3")

    assert get_progress(None) is None


# --- subprocess timeouts (#57: hung whisper-cli blocked forever) -------


def test_both_subprocess_calls_are_bounded_by_a_timeout(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    run_kwargs_log = []
    monkeypatch.setattr(
        "app.services.transcription.subprocess.run",
        _make_fake_afconvert_run(calls, kwargs_log=run_kwargs_log),
    )
    wait_log = []
    monkeypatch.setattr(
        "app.services.transcription.subprocess.Popen",
        _make_fake_popen(calls, _whisper_json_fixture(), wait_log=wait_log),
    )

    transcribe_audio("/fake/input.mp3", language="ja")

    assert isinstance(run_kwargs_log[0].get("timeout"), int | float)
    assert isinstance(wait_log[0], int | float)


def test_afconvert_timeout_raises_transcription_error(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_timeout())

    with pytest.raises(TranscriptionError):
        transcribe_audio("/fake/input.mp3")


def test_whisper_cli_timeout_raises_transcription_error(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr(
        "app.services.transcription.subprocess.Popen",
        _make_fake_popen(calls, timeout_on_first_wait=True),
    )

    with pytest.raises(TranscriptionError):
        transcribe_audio("/fake/input.mp3")


def test_whisper_cli_timeout_includes_partial_stderr_in_error(monkeypatch, tmp_path):
    _stub_model(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr("app.services.transcription.subprocess.run", _make_fake_afconvert_run(calls))
    monkeypatch.setattr(
        "app.services.transcription.subprocess.Popen",
        _make_fake_popen(
            calls,
            timeout_on_first_wait=True,
            stderr_lines=["trying to decode with miniaudio\n"],
        ),
    )

    with pytest.raises(TranscriptionError, match="trying to decode with miniaudio"):
        transcribe_audio("/fake/input.mp3")
