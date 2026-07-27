import pytest

from app.services.rss import classify_transcript_format


@pytest.mark.parametrize(
    ("type_attr", "url", "expected"),
    [
        ("application/x-srt", "https://example.com/foo", "srt"),
        (None, "https://example.com/transcript.vtt", "vtt"),
        ("application/json", "https://example.com/data", "json"),
        (None, "https://example.com/file.json", "json"),
        ("text/html", "https://example.com/page", "html"),
        (None, "https://example.com/transcript.htm", "html"),
        ("text/plain", "https://example.com/file", "text"),
        (None, "https://example.com/file.txt", "text"),
        (None, "https://example.com/file.pdf", "unknown"),
        (None, "https://example.com/", "unknown"),
        ("APPLICATION/SRT", "https://example.com/x", "srt"),
        (None, "https://example.com/FILE.VTT", "vtt"),
    ],
)
def test_classify_transcript_format(type_attr, url, expected):
    assert classify_transcript_format(type_attr, url) == expected


def test_url_extension_takes_precedence_over_conflicting_type_attr():
    # srt is checked before vtt in the branch order, so a `.srt` URL wins
    # even when the declared mime type says vtt.
    assert classify_transcript_format("text/vtt", "https://example.com/file.srt") == "srt"
