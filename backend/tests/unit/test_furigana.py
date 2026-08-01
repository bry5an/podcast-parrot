import re
import shlex

import pytest

from app.services import packs
from app.services.furigana import build_segments

_KANJI_RE = re.compile(r"[一-鿿々]")


def test_empty_text_returns_single_empty_segment():
    assert build_segments("", "ja") == [{"base": "", "reading": ""}]


def test_non_japanese_language_tokenizes_per_word():
    segments = build_segments("Hello world", "en")
    assert segments == [
        {"base": "Hello", "reading": ""},
        {"base": " ", "reading": ""},
        {"base": "world", "reading": ""},
    ]
    assert "".join(s["base"] for s in segments) == "Hello world"


def test_word_tokenization_preserves_punctuation_and_reconstructs_exactly():
    text = "Well, isn't that great?!"
    segments = build_segments(text, "en")
    assert "".join(s["base"] for s in segments) == text
    assert all(s["reading"] == "" for s in segments)
    words = [s["base"] for s in segments if re.match(r"^[A-Za-z]+(?:'[A-Za-z]+)*$", s["base"])]
    assert words == ["Well", "isn't", "that", "great"]


def test_accented_spanish_and_french_words_tokenize_as_single_segments():
    text = "¿Cómo estás? C'est très bien."
    segments = build_segments(text, "es")
    assert "".join(s["base"] for s in segments) == text
    words = [s["base"] for s in segments if re.match(r"^[^\W\d_]+(?:['’][^\W\d_]+)*$", s["base"])]
    assert words == ["Cómo", "estás", "C'est", "très", "bien"]


def test_korean_words_tokenize_as_single_segments():
    text = "안녕하세요, 오늘 날씨가 좋네요!"
    segments = build_segments(text, "ko")
    assert "".join(s["base"] for s in segments) == text
    words = [s["base"] for s in segments if re.match(r"^[^\W\d_]+(?:['’][^\W\d_]+)*$", s["base"])]
    assert words == ["안녕하세요", "오늘", "날씨가", "좋네요"]


def test_japanese_text_with_non_japanese_language_is_not_segmented_by_mecab():
    # The `language` argument drives the tokenization strategy, not the text
    # content itself — Japanese text tagged as English gets the word-boundary
    # tokenizer (a no-op here, since it only splits on A-Za-z runs), not MeCab.
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
