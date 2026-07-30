from app.services.dictionary import DictionaryEntry, DictionarySense


def test_get_dictionary_returns_entry(client, monkeypatch):
    entry = DictionaryEntry(
        word="book", reading=None, senses=[DictionarySense(part_of_speech="Noun", definitions=["a book"])]
    )
    monkeypatch.setattr("app.api.dictionary.dictionary.lookup_word", lambda word, language: entry)

    response = client.get("/api/dictionary", params={"word": "book", "language": "en"})

    assert response.status_code == 200
    assert response.json() == {
        "word": "book",
        "reading": None,
        "senses": [{"part_of_speech": "Noun", "definitions": ["a book"]}],
    }


def test_get_dictionary_returns_404_when_not_found(client, monkeypatch):
    monkeypatch.setattr("app.api.dictionary.dictionary.lookup_word", lambda word, language: None)

    response = client.get("/api/dictionary", params={"word": "asdkfjaslkdfj", "language": "en"})

    assert response.status_code == 404


def test_get_dictionary_requires_word_and_language(client):
    response = client.get("/api/dictionary")

    assert response.status_code == 422
