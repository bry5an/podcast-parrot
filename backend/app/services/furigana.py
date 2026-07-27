import re

import fugashi

_KANJI_RE = re.compile(r"[一-鿿々]")  # CJK ideographs + 々 iteration mark

_tagger = None


def _get_tagger() -> fugashi.Tagger:
    global _tagger
    if _tagger is None:
        _tagger = fugashi.Tagger()
    return _tagger


def _katakana_to_hiragana(katakana: str) -> str:
    return "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in katakana)


def build_segments(text: str, language: str) -> list[dict]:
    """Split `text` into the {base, reading} segments the Shadowing Player
    renders as ruby text. Only Japanese sentences get morpheme-by-morpheme
    furigana; every other language (notably English, the ja_en direction's
    target language) collapses to a single non-furigana segment."""
    if not text:
        return [{"base": text, "reading": ""}]
    if not (language or "").startswith("ja"):
        return [{"base": text, "reading": ""}]

    segments = []
    for word in _get_tagger()(text):
        base = word.surface
        if not base:
            continue
        reading = ""
        if word.feature.kana and _KANJI_RE.search(base):
            reading = _katakana_to_hiragana(word.feature.kana)
        segments.append({"base": base, "reading": reading})
    return segments or [{"base": text, "reading": ""}]
