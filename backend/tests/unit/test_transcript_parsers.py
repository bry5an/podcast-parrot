import json

import pytest

from app.services.transcript_parsers import Cue, parse_json_transcript, parse_srt, parse_vtt


class TestParseSrt:
    def test_parses_indexed_cues_with_comma_ms(self):
        content = (
            "1\n"
            "00:00:01,000 --> 00:00:04,500\n"
            "Hello <i>world</i>\n"
            "\n"
            "2\n"
            "00:00:05,000 --> 00:00:06,000\n"
            "Second line\n"
        )
        cues = parse_srt(content)
        assert cues == [
            Cue(1.0, 4.5, "Hello world"),
            Cue(5.0, 6.0, "Second line"),
        ]

    def test_parses_cues_without_index_line(self):
        content = "00:00:01,000 --> 00:00:02,000\nNo index here\n"
        assert parse_srt(content) == [Cue(1.0, 2.0, "No index here")]

    def test_skips_cues_with_empty_text(self):
        content = "1\n00:00:01,000 --> 00:00:02,000\n\n"
        assert parse_srt(content) == []

    def test_skips_blocks_without_a_timestamp(self):
        content = "This is just a stray note\nwith two lines\n"
        assert parse_srt(content) == []


class TestParseVtt:
    def test_parses_cue_with_leading_identifier_line(self):
        content = "1\n00:00:01.000 --> 00:00:02.000\nText here\n"
        assert parse_vtt(content) == [Cue(1.0, 2.0, "Text here")]

    def test_parses_cue_without_hour_component(self):
        content = "00:05.000 --> 00:10.000\nNo hour\n"
        assert parse_vtt(content) == [Cue(5.0, 10.0, "No hour")]

    def test_ignores_header_block(self):
        content = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n"
        assert parse_vtt(content) == [Cue(1.0, 2.0, "Hello")]

    def test_strips_tags(self):
        content = "00:00:01.000 --> 00:00:02.000\n<b>Bold</b> text\n"
        assert parse_vtt(content) == [Cue(1.0, 2.0, "Bold text")]


class TestParseJsonTranscript:
    def test_parses_valid_segments(self):
        content = json.dumps(
            {
                "segments": [
                    {"startTime": 0.5, "endTime": 1.5, "body": "Hi"},
                    {"startTime": 2, "endTime": 3, "body": ""},
                    {"startTime": 4, "body": "missing end time"},
                ]
            }
        )
        assert parse_json_transcript(content) == [Cue(0.5, 1.5, "Hi")]

    def test_missing_segments_key_returns_empty_list(self):
        assert parse_json_transcript("{}") == []

    def test_malformed_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_json_transcript("not json")
