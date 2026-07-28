import re
import shlex

import pytest

from app.services import packs
from app.services.furigana import build_segments

_KANJI_RE = re.compile(r"[一-鿿々]")


def test_empty_text_returns_single_empty_segment():
    assert build_segments("", "ja") == [{"base": "", "reading": ""}]


def test_non_japanese_language_collapses_to_single_segment():
    assert build_segments("Hello world", "en") == [{"base": "Hello world", "reading": ""}]


def test_japanese_text_with_non_japanese_language_still_collapses():
    # The `language` argument drives the collapse decision, not the text
    # content itself — Japanese text tagged as English stays un-annotated.
    assert build_segments("東京は晴れです", "en") == [{"base": "東京は晴れです", "reading": ""}]


def test_pure_kana_sentence_has_no_readings():
    segments = build_segments("こんにちは", "ja")
    assert segments
    assert all(s["reading"] == "" for s in segments)
    assert "".join(s["base"] for s in segments) == "こんにちは"


def test_degrades_gracefully_without_pack(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.furigana._UNIDIC_DIR", tmp_path / "does-not-exist")
    monkeypatch.setattr("app.services.furigana._tagger", None)

    segments = build_segments("東京は晴れです", "ja")

    assert segments == [{"base": "東京は晴れです", "reading": ""}]


def test_tagger_lazily_picks_up_pack_once_installed(monkeypatch, tmp_path):
    fake_dir = tmp_path / "unidic"
    monkeypatch.setattr("app.services.furigana._UNIDIC_DIR", fake_dir)
    monkeypatch.setattr("app.services.furigana._tagger", None)

    calls = []
    monkeypatch.setattr("app.services.furigana.fugashi.Tagger", lambda arg: calls.append(arg) or object())

    assert build_segments("東京", "ja") == [{"base": "東京", "reading": ""}]
    assert calls == []  # no pack on disk yet: never even tries to construct a Tagger

    fake_dir.mkdir(parents=True)
    (fake_dir / "sys.dic").write_bytes(b"stub")

    class _FakeFeature:
        kana = "トウキョウ"

    class _FakeWord:
        surface = "東京"
        feature = _FakeFeature()

    class _FakeTagger:
        def __call__(self, text):
            return [_FakeWord()]

    monkeypatch.setattr("app.services.furigana.fugashi.Tagger", lambda arg: (calls.append(arg), _FakeTagger())[1])

    segments = build_segments("東京", "ja")
    assert calls == [f"-d {shlex.quote(str(fake_dir))} -r {shlex.quote(str(fake_dir / 'dicrc'))}"]
    assert segments == [{"base": "東京", "reading": "とうきょう"}]

    build_segments("東京", "ja")  # cached: must not reconstruct the tagger
    assert calls == [f"-d {shlex.quote(str(fake_dir))} -r {shlex.quote(str(fake_dir / 'dicrc'))}"]


@pytest.mark.skipif(
    not packs.is_installed("japanese"),
    reason="requires the real japanese language pack installed at KOTOBA_DATA_DIR/packs/unidic",
)
def test_kanji_tokens_get_readings_kana_only_tokens_do_not():
    segments = build_segments("東京は晴れです", "ja")
    assert segments
    for s in segments:
        if _KANJI_RE.search(s["base"]):
            assert s["reading"] != ""
        else:
            assert s["reading"] == ""
    assert "".join(s["base"] for s in segments) == "東京は晴れです"
