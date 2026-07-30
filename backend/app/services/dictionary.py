import re
from urllib.parse import quote

import httpx
from sqlmodel import SQLModel

_TAG_RE = re.compile(r"<[^>]+>")
_USER_AGENT = "podcast-parrot/1.0 (https://github.com/bry5an/podcast-parrot)"


class DictionarySense(SQLModel):
    part_of_speech: str | None
    definitions: list[str]


class DictionaryEntry(SQLModel):
    word: str
    reading: str | None
    senses: list[DictionarySense]


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def _lookup_english(word: str) -> DictionaryEntry | None:
    url = f"https://en.wiktionary.org/api/rest_v1/page/definition/{quote(word)}"
    try:
        response = httpx.get(url, timeout=10.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
        if response.status_code == 404:
            return None
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    data = response.json()
    entries = data.get("en") or []
    senses = []
    for entry in entries:
        definitions = [_strip_html(d["definition"]) for d in entry.get("definitions", []) if d.get("definition")]
        if definitions:
            senses.append(DictionarySense(part_of_speech=entry.get("partOfSpeech"), definitions=definitions))
    if not senses:
        return None
    return DictionaryEntry(word=word, reading=None, senses=senses)


def _lookup_japanese(word: str) -> DictionaryEntry | None:
    url = f"https://jisho.org/api/v1/search/words?keyword={quote(word)}"
    try:
        response = httpx.get(url, timeout=10.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    data = response.json().get("data") or []
    if not data:
        return None

    result = data[0]
    japanese = result.get("japanese") or []
    reading = japanese[0].get("reading") if japanese else None

    senses = []
    for sense in result.get("senses", []):
        definitions = sense.get("english_definitions") or []
        if not definitions:
            continue
        part_of_speech = ", ".join(sense.get("parts_of_speech") or []) or None
        senses.append(DictionarySense(part_of_speech=part_of_speech, definitions=definitions))
    if not senses:
        return None
    return DictionaryEntry(word=word, reading=reading, senses=senses)


def lookup_word(word: str, language: str) -> DictionaryEntry | None:
    if (language or "").startswith("ja"):
        return _lookup_japanese(word)
    return _lookup_english(word)
