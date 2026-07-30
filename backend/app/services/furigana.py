import re
import shlex

import fugashi

from app import paths

_KANJI_RE = re.compile(r"[一-鿿々]")  # CJK ideographs + 々 iteration mark
_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*")
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
    _tagger = fugashi.Tagger(
        f"-d {shlex.quote(str(_UNIDIC_DIR))} -r {shlex.quote(str(_UNIDIC_DIR / 'dicrc'))}"
    )
    return _tagger


def _katakana_to_hiragana(katakana: str) -> str:
    return "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in katakana)


def _tokenize_words(text: str) -> list[dict]:
    """Split non-Japanese text into per-word segments (each a clickable unit
    for dictionary lookup), keeping whitespace/punctuation as separate
    non-word segments so joining every segment's `base` reconstructs `text`
    exactly."""
    segments = []
    pos = 0
    for match in _WORD_RE.finditer(text):
        if match.start() > pos:
            segments.append({"base": text[pos : match.start()], "reading": ""})
        segments.append({"base": match.group(), "reading": ""})
        pos = match.end()
    if pos < len(text):
        segments.append({"base": text[pos:], "reading": ""})
    return segments or [{"base": text, "reading": ""}]


def build_segments(text: str, language: str) -> list[dict]:
    """Split `text` into the {base, reading} segments the Shadowing Player
    renders as ruby text. Japanese sentences get morpheme-by-morpheme
    furigana; every other language (notably English, the ja_en direction's
    target language) gets word-level segments with no readings. Also
    collapses to a single segment when the Japanese language pack (#24)
    isn't installed yet, rather than raising."""
    if not text:
        return [{"base": text, "reading": ""}]
    if not (language or "").startswith("ja"):
        return _tokenize_words(text)

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
