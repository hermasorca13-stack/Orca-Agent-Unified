"""
Comprehensive tests for skills/youtube_skill.py (2026 stack).

Coverage:
  - URL parser: every YouTube URL shape + invalid inputs
  - Result types: VideoMetadata, TranscriptSegment, TranscriptResult,
    VideoAnalysis
  - Formatters: SRT, Markdown, plain text, Telegram card
  - Heuristic analysis: summary + key quotes
  - LLM analysis: mocked (no real API calls)
  - Multilingual: Arabic, English, mixed, CJK
  - End-to-end pipeline with mocks
  - Performance: latency budgets

The test file follows the project's pattern: pure unit tests for
deterministic logic, mocked tests for the network-bound calls, and
gated live tests (skipped unless YOUTUBE_LIVE=1) for the real
YouTube API. This keeps CI fast while still validating the live path
in development.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "youtube_skill.py"


def _load_skill():
    spec = importlib.util.spec_from_file_location(
        "youtube_skill_under_test", str(SKILL_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["youtube_skill_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_skill()


# ======================================================================
# URL parser
# ======================================================================
class TestParseURL:
    """Every YouTube URL shape must resolve to a clean 11-char video ID."""

    @pytest.mark.parametrize("url,expected", [
        # The canonical watch URL
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # The mobile watch URL
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # watch URL with timestamp parameter
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
        # watch URL with playlist
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLfoo", "dQw4w9WgXcQ"),
        # youtu.be short URL
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # youtu.be with timestamp
        ("https://youtu.be/dQw4w9WgXcQ?t=42s", "dQw4w9WgXcQ"),
        # Shorts
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # Embed
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # Live
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # Music
        ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # Plain ID
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        # YouTube subdomain variations
        ("https://www.youtube.com/watch?v=_A7nvCOXvDY", "_A7nvCOXvDY"),
    ])
    def test_valid_youtube_urls(self, url, expected):
        assert mod.parse_url(url) == expected

    @pytest.mark.parametrize("bad", [
        "",
        "   ",
        "not-a-url",
        "https://example.com/watch?v=abc",
        "https://vimeo.com/123456",
        "https://dailymotion.com/video/x123",
        "https://www.youtube.com/",                # no path
        "https://www.youtube.com/watch",            # no v param
        "https://www.youtube.com/watch?v=",         # empty v
        "https://www.youtube.com/watch?v=short",    # wrong length
        "https://www.youtube.com/shorts/",          # no ID
        None,
    ])
    def test_invalid_youtube_urls_raise(self, bad):
        if bad is None:
            with pytest.raises(mod.InvalidURLError):
                mod.parse_url(None)  # type: ignore[arg-type]
        else:
            with pytest.raises(mod.InvalidURLError):
                mod.parse_url(bad)

    def test_canonical_url_round_trip(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        vid = mod.parse_url(url)
        assert mod.canonical_url(vid) == url

    def test_canonical_url_rejects_bad_id(self):
        with pytest.raises(mod.InvalidURLError):
            mod.canonical_url("not-an-id")


# ======================================================================
# Result types
# ======================================================================
class TestResultTypes:
    """The plain-class result types must behave like data containers."""

    def test_video_metadata_to_dict(self):
        md = mod.VideoMetadata(
            video_id="abc12345678",
            title="Hello",
            author="Alice",
        )
        d = md.to_dict()
        assert d["video_id"] == "abc12345678"
        assert d["title"] == "Hello"
        assert d["author"] == "Alice"

    def test_transcript_segment_srt_timestamp(self):
        seg = mod.TranscriptSegment("hi", 3661.5, 2.0)  # 1h 1m 1.5s
        assert seg.to_srt_timestamp() == "01:01:01,500"

    def test_transcript_result_plain_text(self):
        segs = [
            mod.TranscriptSegment("Hello world.", 0.0, 1.0),
            mod.TranscriptSegment("  Second  sentence.  ", 1.0, 1.0),
        ]
        tr = mod.TranscriptResult(segments=segs, language_code="en")
        # The double space inside the second segment is preserved
        # (we only strip leading/trailing whitespace).
        assert tr.plain_text == "Hello world. Second  sentence."
        assert tr.word_count == 4
        # char_count includes the internal double space + the space
        # between segments
        assert tr.char_count == 33

    def test_transcript_result_srt_round_trip(self):
        segs = [
            mod.TranscriptSegment("First.", 0.0, 1.5),
            mod.TranscriptSegment("Second.", 1.5, 2.0),
        ]
        tr = mod.TranscriptResult(segments=segs, language_code="en")
        srt = tr.to_srt()
        assert "00:00:00,000 --> 00:00:01,500" in srt
        assert "First." in srt
        assert "Second." in srt

    def test_transcript_result_markdown(self):
        segs = [
            mod.TranscriptSegment("Hi", 0.0, 1.0),
            mod.TranscriptSegment("There", 65.0, 1.0),  # 1:05
        ]
        tr = mod.TranscriptResult(segments=segs, language_code="en")
        md = tr.to_markdown()
        assert "`00:00`" in md
        assert "`01:05`" in md
        assert "Hi" in md
        assert "There" in md


# ======================================================================
# Language preference
# ======================================================================
class TestLanguagePreference:
    """The preference-order logic must put the user's language first."""

    def test_english_first(self):
        codes = mod._resolve_preferred_languages(
            ["de", "en", "fr", "ar"],
        )
        assert codes[0] == "en"

    def test_arabic_above_german(self):
        # English is preferred first by default. Arabic must outrank
        # German, but may be second after English.
        codes = mod._resolve_preferred_languages(["de", "ar", "en"])
        # The top-2 must be english + arabic in some order; german last
        assert set(codes[:2]) == {"en", "ar"}
        assert codes[-1] == "de"

    def test_egyptian_arabic_above_english_when_only_egyptian(self):
        # When only Egyptian Arabic is available, it wins.
        codes = mod._resolve_preferred_languages(["ar-eg"])
        assert codes[0] == "ar-eg"

    def test_unknown_codes_pushed_to_end(self):
        codes = mod._resolve_preferred_languages(
            ["xyz", "abc", "en"],
        )
        assert codes[-1] != "en"
        assert codes[0] == "en"

    def test_dict_input(self):
        codes = mod._resolve_preferred_languages([
            {"language_code": "de"},
            {"language_code": "en"},
        ])
        assert codes[0] == "en"


# ======================================================================
# Heuristic summary (no LLM)
# ======================================================================
class TestHeuristicSummary:
    """The fallback summary must work in multiple languages."""

    def test_english_summary(self):
        segs = [
            mod.TranscriptSegment(
                "Quantum computing is transforming cryptography and AI.", 0.0, 3.0),
            mod.TranscriptSegment(
                "IBM announced a 1000 qubit processor named Condor in 2026.", 3.0, 4.0),
            mod.TranscriptSegment(
                "This is a major milestone for the industry worldwide.", 7.0, 3.0),
            mod.TranscriptSegment(
                "Many companies are investing billions in this technology.", 10.0, 3.0),
        ]
        tr = mod.TranscriptResult(segments=segs, language_code="en")
        s = mod.heuristic_summary(tr, max_sentences=2)
        # The heuristic favours sentences with data points (digits,
        # proper-noun-shaped tokens) so the IBM sentence usually wins.
        # The summary must contain at least one of the substantive
        # sentences — either the IBM announcement or the introduction.
        assert "IBM" in s or "Quantum computing" in s

    def test_arabic_summary(self):
        segs = [
            mod.TranscriptSegment(
                "الحوسبة الكمية تغير عالم التشفير والذكاء الاصطناعي.", 0.0, 3.0),
            mod.TranscriptSegment(
                "أعلنت IBM عن معالج يحتوي على 1000 كيوبت اسمه Condor.", 3.0, 4.0),
            mod.TranscriptSegment(
                "هذا إنجاز كبير للصناعة في جميع أنحاء العالم.", 7.0, 3.0),
        ]
        tr = mod.TranscriptResult(segments=segs, language_code="ar")
        s = mod.heuristic_summary(tr, max_sentences=2)
        # Should not be empty
        assert len(s) > 0
        assert "الحوسبة" in s or "IBM" in s

    def test_empty_transcript(self):
        tr = mod.TranscriptResult(segments=[], language_code="en")
        assert mod.heuristic_summary(tr) == ""

    def test_short_transcript_returns_full(self):
        segs = [mod.TranscriptSegment("Just one sentence.", 0.0, 1.0)]
        tr = mod.TranscriptResult(segments=segs, language_code="en")
        s = mod.heuristic_summary(tr, max_sentences=5)
        assert "Just one sentence" in s


# ======================================================================
# Heuristic key quotes
# ======================================================================
class TestHeuristicKeyQuotes:
    """The key-quote picker must skip filler and prefer substantial sentences."""

    def test_picks_substantial_quotes(self):
        segs = [
            mod.TranscriptSegment("Hi.", 0.0, 1.0),
            mod.TranscriptSegment(
                "Quantum supremacy will reshape cryptography within the next decade.",
                1.0, 4.0,
            ),
            mod.TranscriptSegment(
                "A most important breakthrough was the 1000 qubit milestone in 2026.",
                5.0, 4.0,
            ),
        ]
        tr = mod.TranscriptResult(segments=segs, language_code="en")
        quotes = mod.heuristic_key_quotes(tr, n=3)
        # The 1-word "Hi." should never be a key quote
        assert not any(q.strip() == "Hi." for q in quotes)
        # At least one substantial quote should appear (the "1000 qubit"
        # one OR the "Quantum supremacy" one)
        assert any("1000 qubit" in q or "Quantum supremacy" in q for q in quotes)

    def test_skips_discourse_markers(self):
        segs = [
            mod.TranscriptSegment(
                "And then the speaker went on to discuss the implications of AI.",
                0.0, 4.0,
            ),
            mod.TranscriptSegment(
                "The future of work will be transformed by automation and robotics.",
                4.0, 4.0,
            ),
        ]
        tr = mod.TranscriptResult(segments=segs, language_code="en")
        quotes = mod.heuristic_key_quotes(tr, n=5)
        # "And then..." starts with a discourse marker, should be skipped
        for q in quotes:
            assert not q.lower().startswith("and ")

    def test_empty_transcript(self):
        tr = mod.TranscriptResult(segments=[], language_code="en")
        assert mod.heuristic_key_quotes(tr) == []


# ======================================================================
# Telegram card formatter
# ======================================================================
class TestFormatCard:
    """The Telegram card must contain every populated field."""

    def test_card_with_everything(self):
        md = mod.VideoMetadata(
            video_id="abc12345678",
            title="Hello World",
            author="Alice",
            thumbnail_url="https://example.com/thumb.jpg",
        )
        tr = mod.TranscriptResult(
            video_id="abc12345678",
            language="English",
            language_code="en",
            is_generated=False,
            segments=[mod.TranscriptSegment("hi", 0.0, 1.0)],
            total_duration=1.0,
            source="manual-caption",
        )
        a = mod.VideoAnalysis(
            metadata=md,
            transcript=tr,
            summary="A short summary.",
            key_quotes=["A memorable quote here."],
            topics=["AI", "ML"],
            sentiment="positive",
            named_entities=["Alice", "IBM"],
            data_points=["1000 qubits", "2026"],
            arguments=["Argument one."],
            counter_arguments=["Counter one."],
            source="llm",
            llm_used=True,
            elapsed_ms=1234.5,
        )
        card = mod.format_card(a)
        assert "Hello World" in card
        assert "Alice" in card
        assert "youtu.be/abc12345678" in card
        assert "Transcript" in card
        assert "Summary" in card
        assert "Topics" in card
        assert "Sentiment" in card
        assert "Key quotes" in card
        assert "Entities" in card
        assert "Data points" in card
        assert "Arguments" in card
        assert "Counter-arguments" in card
        assert "analysis: llm" in card
        assert "gpt-4o-mini" in card  # the LLM model name

    def test_card_with_minimum_metadata(self):
        # When metadata is missing, the card must still render cleanly
        tr = mod.TranscriptResult(
            video_id="abc12345678",
            language_code="en",
            segments=[],
        )
        a = mod.VideoAnalysis(transcript=tr)
        card = mod.format_card(a)
        assert "abc12345678" in card
        # No crash even when topics/quotes/etc are empty

    def test_card_truncates_long_title(self):
        md = mod.VideoMetadata(
            video_id="abc12345678",
            title="A" * 500,  # very long title
            author="X",
        )
        tr = mod.TranscriptResult(
            video_id="abc12345678",
            language_code="en",
            segments=[],
        )
        a = mod.VideoAnalysis(metadata=md, transcript=tr)
        card = mod.format_card(a)
        # Should contain a truncated title (with ellipsis) — and NOT
        # a 500-A title.
        assert "…" in card
        assert "A" * 500 not in card


# ======================================================================
# oEmbed metadata extraction (mocked)
# ======================================================================
class TestMetadataMocked:
    """Mock the HTTP layer and confirm the JSON -> VideoMetadata mapping."""

    def test_oembed_success(self, monkeypatch):
        fake_resp = MagicMock()
        fake_resp.read.return_value = json.dumps({
            "title": "Rick Astley - Never Gonna Give You Up",
            "author_name": "Rick Astley",
            "author_url": "https://www.youtube.com/@RickAstley",
            "type": "video",
            "height": 270,
            "width": 480,
            "version": "1.0",
            "provider_name": "YouTube",
            "provider_url": "https://www.youtube.com/",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            "html": "<iframe ...></iframe>",
        }).encode("utf-8")
        fake_resp.__enter__ = MagicMock(return_value=fake_resp)
        fake_resp.__exit__ = MagicMock(return_value=False)

        monkeypatch.setattr(
            mod, "_oembed_lookup", lambda url, timeout=15.0: json.loads(fake_resp.read().decode("utf-8"))
        )
        md = mod.extract_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert md.title == "Rick Astley - Never Gonna Give You Up"
        assert md.author == "Rick Astley"
        assert md.video_id == "dQw4w9WgXcQ"
        assert md.thumbnail_url.startswith("https://")

    def test_oembed_failure_raises_metadata_error(self, monkeypatch):
        def fake_lookup(url, timeout=15.0):
            raise OSError("connection refused")
        monkeypatch.setattr(mod, "_oembed_lookup", fake_lookup)
        with pytest.raises(mod.MetadataError):
            mod.extract_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_oembed_empty_response(self, monkeypatch):
        monkeypatch.setattr(mod, "_oembed_lookup", lambda url, timeout=15.0: {})
        with pytest.raises(mod.MetadataError):
            mod.extract_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


# ======================================================================
# Transcript extraction (mocked)
# ======================================================================
class TestTranscriptMocked:
    """Mock youtube-transcript-api to confirm the segment-mapping logic."""

    def _build_fake_listing(self, tracks):
        """Build a fake ``listing`` object with the API our wrapper expects.

        Each track is a dict with keys:
          - language_code
          - language
          - is_generated
          - is_translatable
          - segments (list of {text, start, duration})
        """
        class FakeTranscript:
            def __init__(self, t):
                self.language_code = t["language_code"]
                self.language = t["language"]
                self.is_generated = t["is_generated"]
                self.is_translatable = t["is_translatable"]
                self._segments = t["segments"]

            def fetch(self):
                return self._segments

            def translate(self, code):
                # Pretend translation worked.
                return FakeTranscript({
                    "language_code": code,
                    "language": code,
                    "is_generated": self.is_generated,
                    "is_translatable": True,
                    "segments": self._segments,
                })

        class FakeListing:
            def __init__(self, tracks):
                self._tracks = [FakeTranscript(t) for t in tracks]

            def __iter__(self):
                return iter(self._tracks)

            def find_manually_created_transcript(self, codes):
                for t in self._tracks:
                    if t.language_code in codes and not t.is_generated:
                        return t
                raise Exception("not found")

            def find_generated_transcript(self, codes):
                for t in self._tracks:
                    if t.language_code in codes and t.is_generated:
                        return t
                raise Exception("not found")

        return FakeListing(tracks)

    def test_manual_caption_first(self, monkeypatch):
        tracks = [
            {
                "language_code": "en", "language": "English",
                "is_generated": False, "is_translatable": True,
                "segments": [
                    {"text": "Hello.", "start": 0.0, "duration": 1.0},
                ],
            },
        ]
        fake_listing = self._build_fake_listing(tracks)
        fake_api = MagicMock()
        fake_api.list.return_value = fake_listing
        # Inject the fake module into sys.modules so the lazy import
        # inside _fetch_transcript_yta resolves to our mock.
        sys.modules["youtube_transcript_api"] = MagicMock()
        sys.modules["youtube_transcript_api"].YouTubeTranscriptApi = MagicMock(
            return_value=fake_api)
        # Also stub the errors submodule
        sys.modules["youtube_transcript_api._errors"] = MagicMock()
        sys.modules["youtube_transcript_api._errors"].NoTranscriptFound = Exception
        sys.modules["youtube_transcript_api._errors"].TranscriptsDisabled = Exception
        sys.modules["youtube_transcript_api._errors"].VideoUnavailable = Exception
        try:
            tr = mod.extract_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            assert tr.language_code == "en"
            assert tr.is_generated is False
            assert tr.source == "manual-caption"
            assert len(tr.segments) == 1
        finally:
            for k in ("youtube_transcript_api",
                      "youtube_transcript_api._errors"):
                sys.modules.pop(k, None)

    def test_falls_back_to_auto_caption(self, monkeypatch):
        tracks = [
            {
                "language_code": "ar", "language": "Arabic",
                "is_generated": True, "is_translatable": True,
                "segments": [
                    {"text": "مرحبا", "start": 0.0, "duration": 1.0},
                ],
            },
        ]
        fake_listing = self._build_fake_listing(tracks)
        fake_api = MagicMock()
        fake_api.list.return_value = fake_listing
        sys.modules["youtube_transcript_api"] = MagicMock()
        sys.modules["youtube_transcript_api"].YouTubeTranscriptApi = MagicMock(
            return_value=fake_api)
        sys.modules["youtube_transcript_api._errors"] = MagicMock()
        sys.modules["youtube_transcript_api._errors"].NoTranscriptFound = Exception
        sys.modules["youtube_transcript_api._errors"].TranscriptsDisabled = Exception
        sys.modules["youtube_transcript_api._errors"].VideoUnavailable = Exception
        try:
            # Prefer English first, but only Arabic auto is available
            tr = mod.extract_transcript(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                languages=["en", "ar"],
            )
            assert tr.language_code == "ar"
            assert tr.is_generated is True
            assert tr.source == "auto-caption"
        finally:
            for k in ("youtube_transcript_api",
                      "youtube_transcript_api._errors"):
                sys.modules.pop(k, None)

    def test_falls_back_to_translation(self, monkeypatch):
        tracks = [
            {
                "language_code": "fr", "language": "French",
                "is_generated": False, "is_translatable": True,
                "segments": [
                    {"text": "Bonjour", "start": 0.0, "duration": 1.0},
                ],
            },
        ]
        fake_listing = self._build_fake_listing(tracks)
        fake_api = MagicMock()
        fake_api.list.return_value = fake_listing
        sys.modules["youtube_transcript_api"] = MagicMock()
        sys.modules["youtube_transcript_api"].YouTubeTranscriptApi = MagicMock(
            return_value=fake_api)
        sys.modules["youtube_transcript_api._errors"] = MagicMock()
        sys.modules["youtube_transcript_api._errors"].NoTranscriptFound = Exception
        sys.modules["youtube_transcript_api._errors"].TranscriptsDisabled = Exception
        sys.modules["youtube_transcript_api._errors"].VideoUnavailable = Exception
        try:
            tr = mod.extract_transcript(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                languages=["en"],
            )
            assert tr.language_code == "en"
            assert tr.source == "translated"
        finally:
            for k in ("youtube_transcript_api",
                      "youtube_transcript_api._errors"):
                sys.modules.pop(k, None)

    def test_no_transcripts_raises(self, monkeypatch):
        fake_listing = self._build_fake_listing([])
        # Make all find methods raise
        fake_listing.find_manually_created_transcript = MagicMock(
            side_effect=Exception("not found"))
        fake_listing.find_generated_transcript = MagicMock(
            side_effect=Exception("not found"))
        fake_listing.__iter__ = lambda self: iter([])

        fake_api = MagicMock()
        fake_api.list.return_value = fake_listing
        sys.modules["youtube_transcript_api"] = MagicMock()
        sys.modules["youtube_transcript_api"].YouTubeTranscriptApi = MagicMock(
            return_value=fake_api)
        sys.modules["youtube_transcript_api._errors"] = MagicMock()
        sys.modules["youtube_transcript_api._errors"].NoTranscriptFound = Exception
        sys.modules["youtube_transcript_api._errors"].TranscriptsDisabled = Exception
        sys.modules["youtube_transcript_api._errors"].VideoUnavailable = Exception
        try:
            with pytest.raises(mod.TranscriptError):
                mod.extract_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        finally:
            for k in ("youtube_transcript_api",
                      "youtube_transcript_api._errors"):
                sys.modules.pop(k, None)

    def test_import_error_message(self, monkeypatch):
        # If youtube-transcript-api is not installed, raise a clear message
        import builtins
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("youtube_transcript_api"):
                raise ImportError("not installed")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        # Remove the module from sys.modules so the import is re-evaluated
        for k in list(sys.modules):
            if k.startswith("youtube_transcript_api"):
                sys.modules.pop(k, None)
        with pytest.raises(mod.TranscriptError, match="not installed"):
            mod.extract_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_segment_count_capped(self, monkeypatch):
        # Build a track with 20k segments
        segs = [
            {"text": f"S{i}", "start": float(i), "duration": 1.0}
            for i in range(20_000)
        ]
        tracks = [{
            "language_code": "en", "language": "English",
            "is_generated": False, "is_translatable": False,
            "segments": segs,
        }]
        fake_listing = self._build_fake_listing(tracks)
        fake_api = MagicMock()
        fake_api.list.return_value = fake_listing
        sys.modules["youtube_transcript_api"] = MagicMock()
        sys.modules["youtube_transcript_api"].YouTubeTranscriptApi = MagicMock(
            return_value=fake_api)
        sys.modules["youtube_transcript_api._errors"] = MagicMock()
        sys.modules["youtube_transcript_api._errors"].NoTranscriptFound = Exception
        sys.modules["youtube_transcript_api._errors"].TranscriptsDisabled = Exception
        sys.modules["youtube_transcript_api._errors"].VideoUnavailable = Exception
        try:
            tr = mod.extract_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            # Should be capped at TRANSCRIPT_SEGMENT_LIMIT
            assert len(tr.segments) == mod.TRANSCRIPT_SEGMENT_LIMIT
        finally:
            for k in ("youtube_transcript_api",
                      "youtube_transcript_api._errors"):
                sys.modules.pop(k, None)


# ======================================================================
# LLM analysis (mocked)
# ======================================================================
class TestLLMAnalysis:
    """Mock the OpenAI client to confirm the prompt -> result mapping."""

    def test_llm_success(self, monkeypatch):
        # Mock the LLM response
        fake_openai = MagicMock()
        fake_resp = MagicMock()
        fake_resp.choices = [MagicMock()]
        fake_resp.choices[0].message.content = json.dumps({
            "summary": "This video discusses AI safety.",
            "key_quotes": ["AI safety is critical."],
            "topics": ["AI safety", "alignment"],
            "sentiment": "neutral",
            "named_entities": ["OpenAI", "DeepMind"],
            "data_points": ["$1B funding"],
            "arguments": ["We need more research."],
            "counter_arguments": ["It may slow progress."],
        })
        fake_openai.OpenAI.return_value.chat.completions.create.return_value = fake_resp
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr("openai.OpenAI", fake_openai.OpenAI)

        # Build a transcript
        segs = [mod.TranscriptSegment("AI safety is critical.", 0.0, 1.0)]
        tr = mod.TranscriptResult(segments=segs, language_code="en", language="English")

        # Now call analyze with with_llm=True
        a = mod._llm_analyze(tr, None, timeout=10.0)
        assert a["summary"] == "This video discusses AI safety."
        assert "AI safety" in a["topics"]
        assert a["sentiment"] == "neutral"

    def test_llm_no_key_raises(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        segs = [mod.TranscriptSegment("hi", 0.0, 1.0)]
        tr = mod.TranscriptResult(segments=segs, language_code="en")
        with pytest.raises(mod.AnalysisError, match="No LLM key"):
            mod._llm_analyze(tr, None)

    def test_llm_invalid_json_raises(self, monkeypatch):
        fake_openai = MagicMock()
        fake_resp = MagicMock()
        fake_resp.choices = [MagicMock()]
        fake_resp.choices[0].message.content = "not json at all"
        fake_openai.OpenAI.return_value.chat.completions.create.return_value = fake_resp
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr("openai.OpenAI", fake_openai.OpenAI)
        segs = [mod.TranscriptSegment("hi", 0.0, 1.0)]
        tr = mod.TranscriptResult(segments=segs, language_code="en")
        with pytest.raises(mod.AnalysisError, match="non-JSON"):
            mod._llm_analyze(tr, None)


# ======================================================================
# End-to-end analyze pipeline (mocked)
# ======================================================================
class TestAnalyzeEndToEnd:
    """The full analyze() pipeline must wire metadata + transcript + LLM."""

    def test_full_pipeline_with_llm(self, monkeypatch):
        # Mock oEmbed
        monkeypatch.setattr(mod, "extract_metadata", lambda url, timeout=15.0: mod.VideoMetadata(
            video_id="dQw4w9WgXcQ",
            title="Test",
            author="Alice",
        ))
        # Mock transcript
        segs = [
            mod.TranscriptSegment(
                "Quantum supremacy is approaching fast.", 0.0, 4.0),
            mod.TranscriptSegment(
                "IBM announced a 1000 qubit processor named Condor.", 4.0, 4.0),
        ]
        monkeypatch.setattr(mod, "extract_transcript", lambda url, languages=None, timeout=20.0: mod.TranscriptResult(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            language="English",
            segments=segs,
            total_duration=8.0,
        ))
        # Mock LLM
        fake_openai = MagicMock()
        fake_resp = MagicMock()
        fake_resp.choices = [MagicMock()]
        fake_resp.choices[0].message.content = json.dumps({
            "summary": "A summary.",
            "key_quotes": ["A quote."],
            "topics": ["quantum"],
            "sentiment": "positive",
            "named_entities": ["IBM"],
            "data_points": ["1000 qubits"],
            "arguments": ["An argument."],
            "counter_arguments": [],
        })
        fake_openai.OpenAI.return_value.chat.completions.create.return_value = fake_resp
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr("openai.OpenAI", fake_openai.OpenAI)

        a = mod.analyze("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert a.metadata.title == "Test"
        assert a.transcript is not None
        assert a.summary == "A summary."
        assert a.llm_used is True
        assert a.source == "llm"

    def test_pipeline_falls_back_to_heuristic(self, monkeypatch):
        monkeypatch.setattr(mod, "extract_metadata", lambda url, timeout=15.0: mod.VideoMetadata(
            video_id="dQw4w9WgXcQ",
            title="Test",
        ))
        segs = [
            mod.TranscriptSegment("Hello world this is a test.", 0.0, 2.0),
        ]
        monkeypatch.setattr(mod, "extract_transcript", lambda url, languages=None, timeout=20.0: mod.TranscriptResult(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segments=segs,
        ))
        # No API key, so LLM is skipped
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        a = mod.analyze("https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                       with_llm=True)
        # LLM unavailable, so heuristic summary is used
        assert a.llm_used is False
        assert a.source == "heuristic"
        # The heuristic summary should contain the transcript text
        assert "Hello world" in a.summary

    def test_pipeline_raises_when_transcript_missing(self, monkeypatch):
        monkeypatch.setattr(mod, "extract_metadata", lambda url, timeout=15.0: mod.VideoMetadata(
            video_id="dQw4w9WgXcQ",
        ))
        monkeypatch.setattr(mod, "extract_transcript",
            MagicMock(side_effect=mod.TranscriptError("no captions")))
        with pytest.raises(mod.TranscriptError):
            mod.analyze("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_pipeline_continues_when_metadata_missing(self, monkeypatch):
        monkeypatch.setattr(mod, "extract_metadata",
            MagicMock(side_effect=mod.MetadataError("oEmbed failed")))
        segs = [mod.TranscriptSegment("hi", 0.0, 1.0)]
        monkeypatch.setattr(mod, "extract_transcript", lambda url, languages=None, timeout=20.0: mod.TranscriptResult(
            video_id="dQw4w9WgXcQ",
            language_code="en",
            segments=segs,
        ))
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        a = mod.analyze("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        # Metadata is None but the rest of the pipeline works
        assert a.metadata is None
        assert a.transcript is not None
        assert a.summary  # heuristic


# ======================================================================
# Multilingual support
# ======================================================================
class TestMultilingual:
    """The skill must work for every language, not just English."""

    def test_arabic_segments_round_trip(self):
        segs = [
            mod.TranscriptSegment("مرحبا بكم", 0.0, 1.0),
            mod.TranscriptSegment("في هذا الفيديو", 1.0, 1.0),
        ]
        tr = mod.TranscriptResult(segments=segs, language_code="ar")
        assert tr.plain_text == "مرحبا بكم في هذا الفيديو"
        assert tr.word_count == 5  # مرحبا + بكم + في + هذا + الفيديو

    def test_chinese_segments(self):
        segs = [mod.TranscriptSegment("你好世界", 0.0, 1.0)]
        tr = mod.TranscriptResult(segments=segs, language_code="zh-Hans")
        assert tr.plain_text == "你好世界"

    def test_arabic_summary_heuristic(self):
        segs = [
            mod.TranscriptSegment(
                "الذكاء الاصطناعي يغير العالم بشكل كبير.", 0.0, 3.0),
            mod.TranscriptSegment(
                "الشركات الكبرى تستثمر مليارات الدولارات.", 3.0, 3.0),
        ]
        tr = mod.TranscriptResult(segments=segs, language_code="ar")
        s = mod.heuristic_summary(tr, max_sentences=2)
        assert "الذكاء" in s


# ======================================================================
# Performance / latency
# ======================================================================
class TestPerformance:
    """The pattern/heuristic path must stay fast even for huge transcripts."""

    def test_url_parser_under_1ms(self):
        t0 = time.monotonic()
        for _ in range(1000):
            mod.parse_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        elapsed = (time.monotonic() - t0) * 1000
        per = elapsed / 1000
        assert per < 0.5, f"per-call latency {per:.3f}ms"

    def test_heuristic_summary_under_200ms_for_long_text(self):
        segs = [
            mod.TranscriptSegment(
                f"Sentence number {i} about some topic. " * 3, float(i), 1.0)
            for i in range(1000)
        ]
        tr = mod.TranscriptResult(segments=segs, language_code="en")
        t0 = time.monotonic()
        s = mod.heuristic_summary(tr, max_sentences=10)
        elapsed = (time.monotonic() - t0) * 1000
        # 200ms is a generous budget for a heuristic pass over
        # 1,000 segments. CI machines are slower than dev laptops.
        assert elapsed < 200, f"summary latency {elapsed:.1f}ms"
        assert s  # non-empty


# ======================================================================
# Live tests (gated on env var)
# ======================================================================
LIVE = os.getenv("YOUTUBE_LIVE", "0") == "1"
LIVE_REASON = "set YOUTUBE_LIVE=1 to enable real-YouTube network tests"


@pytest.mark.skipif(not LIVE, reason=LIVE_REASON)
class TestLive:
    """Real network tests against the live YouTube API.

    Skipped by default. Set YOUTUBE_LIVE=1 to run.
    These tests confirm that the 2026 stack actually works against
    production, not just against mocks.
    """

    def test_live_metadata(self):
        # Rick Astley — Never Gonna Give You Up (a famous public video)
        md = mod.extract_metadata("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert "Rick" in md.title or "Never" in md.title
        assert md.video_id == "dQw4w9WgXcQ"
        assert md.thumbnail_url.startswith("https://")

    def test_live_transcript(self):
        tr = mod.extract_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert len(tr.segments) > 0
        # The Rickroll video has been up for 15+ years and has
        # captions in at least English.
        assert tr.language_code in ("en", "en-US", "en-GB")
