import httpx

from app.services.dictionary import lookup_word


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


_WIKTIONARY_BOOK = {
    "en": [
        {
            "partOfSpeech": "Noun",
            "definitions": [
                {"definition": ""},
                {"definition": "A collection of sheets of paper bound together, containing <b>printed</b> text."},
            ],
        }
    ]
}

_JISHO_BOOK = {
    "data": [
        {
            "japanese": [{"word": "本", "reading": "ほん"}],
            "senses": [
                {"english_definitions": ["book", "volume"], "parts_of_speech": ["Noun"]},
                {"english_definitions": [], "parts_of_speech": ["Prefix"]},
            ],
        }
    ]
}


def test_lookup_english_word_strips_html_and_skips_empty_definitions(monkeypatch):
    monkeypatch.setattr("app.services.dictionary.httpx.get", lambda *a, **k: _FakeResponse(_WIKTIONARY_BOOK))

    entry = lookup_word("book", "en")

    assert entry is not None
    assert entry.word == "book"
    assert entry.reading is None
    assert [s.model_dump() for s in entry.senses] == [
        {
            "part_of_speech": "Noun",
            "definitions": ["A collection of sheets of paper bound together, containing printed text."],
        }
    ]


def test_lookup_english_word_not_found_returns_none(monkeypatch):
    monkeypatch.setattr("app.services.dictionary.httpx.get", lambda *a, **k: _FakeResponse({}, status_code=404))

    assert lookup_word("asdkfjaslkdfj", "en") is None


def test_lookup_english_word_network_error_returns_none(monkeypatch):
    def raise_error(*args, **kwargs):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("app.services.dictionary.httpx.get", raise_error)

    assert lookup_word("book", "en") is None


def test_lookup_japanese_word_returns_reading_and_senses(monkeypatch):
    monkeypatch.setattr("app.services.dictionary.httpx.get", lambda *a, **k: _FakeResponse(_JISHO_BOOK))

    entry = lookup_word("本", "ja")

    assert entry is not None
    assert entry.word == "本"
    assert entry.reading == "ほん"
    assert [s.model_dump() for s in entry.senses] == [{"part_of_speech": "Noun", "definitions": ["book", "volume"]}]


def test_lookup_japanese_word_not_found_returns_none(monkeypatch):
    monkeypatch.setattr("app.services.dictionary.httpx.get", lambda *a, **k: _FakeResponse({"data": []}))

    assert lookup_word("asdkfjaslkdfj", "ja") is None


def test_lookup_japanese_word_network_error_returns_none(monkeypatch):
    def raise_error(*args, **kwargs):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("app.services.dictionary.httpx.get", raise_error)

    assert lookup_word("本", "ja") is None
