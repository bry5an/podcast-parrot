import re

import fugashi

from app import paths

_KANJI_RE = re.compile(r"[一-鿿々]")  # CJK ideographs + 々 iteration mark
_UNIDIC_DIR = paths.packs_dir() / "unidic"

_tagger: fugashi.Tagger | None = None


def _get_tagger() -> fugashi.Tagger | None:
    global _tagger
    if _tagger is not None:
        return _tagger
    if not (_UNIDIC_DIR / "sys.dic").is_file():
        return None
    # -r must be passed explicitly: unlike the old bundled-dictionary setup,
    # MeCab won't infer dicdir/dicrc from -d alone and instead tries (and
    # fails) to load a system-wide mecabrc.
    _tagger = fugashi.Tagger(f"-d {_UNIDIC_DIR} -r {_UNIDIC_DIR / 'dicrc'}")
    return _tagger


def _katakana_to_hiragana(katakana: str) -> str:
    return "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in katakana)


def build_segments(text: str, language: str) -> list[dict]:
    """Split `text` into the {base, reading} segments the Shadowing Player
    renders as ruby text. Only Japanese sentences get morpheme-by-morpheme
    furigana; every other language (notably English, the ja_en direction's
    target language) collapses to a single non-furigana segment. Also
    collapses to a single segment when the Japanese language pack (#24)
    isn't installed yet, rather than raising."""
    if not text:
        return [{"base": text, "reading": ""}]
    if not (language or "").startswith("ja"):
        return [{"base": text, "reading": ""}]

    tagger = _get_tagger()
    if tagger is None:
        return [{"base": text, "reading": ""}]

    segments = []
    for word in tagger(text):
        base = word.surface
        if not base:
            continue
        reading = ""
        if word.feature.kana and _KANJI_RE.search(base):
            reading = _katakana_to_hiragana(word.feature.kana)
        segments.append({"base": base, "reading": reading})
    return segments or [{"base": text, "reading": ""}]
