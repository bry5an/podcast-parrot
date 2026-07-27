import re

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


def test_kanji_tokens_get_readings_kana_only_tokens_do_not():
    segments = build_segments("東京は晴れです", "ja")
    assert segments
    for s in segments:
        if _KANJI_RE.search(s["base"]):
            assert s["reading"] != ""
        else:
            assert s["reading"] == ""
    assert "".join(s["base"] for s in segments) == "東京は晴れです"
