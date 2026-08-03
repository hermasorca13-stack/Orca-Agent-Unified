"""
Tests for skills/transcribe_skill.py.

Two layers:
- Unit tests: mock the OpenAI client. No network. Run anywhere.
- Integration test: real API call. Skipped when OPENAI_API_KEY is missing
  or when explicitly opted out via env.

Run with:
    python -m pytest tests/test_transcribe_skill.py -v
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ----------------------------------------------------------------------
# Load the skill module under a synthetic name so we don't pull the
# skills/__init__.py chain (which requires every dependency to be
# installed in the test env).
# ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "transcribe_skill.py"


def _load_skill():
    spec = importlib.util.spec_from_file_location(
        "transcribe_skill_under_test", str(SKILL_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["transcribe_skill_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_skill()
transcribe = mod.transcribe
format_card = mod.format_card
TranscribeError = mod.TranscribeError
SUPPORTED_EXTS = mod.SUPPORTED_EXTS
MAX_BYTES = mod.MAX_BYTES


# ----------------------------------------------------------------------
# Unit tests
# ----------------------------------------------------------------------
class TestResolution:
    def test_missing_file_raises(self, monkeypatch):
        # Set a dummy key so the file-check path runs.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-for-tests")
        with pytest.raises(TranscribeError, match="File not found"):
            transcribe("/nonexistent/never.ogg")

    def test_unsupported_extension_raises(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-for-tests")
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"data")
            p = f.name
        try:
            with pytest.raises(TranscribeError, match="Unsupported extension"):
                transcribe(p)
        finally:
            os.unlink(p)

    def test_oversize_bytes_falls_back_offline(self):
        # 2026-08-03: when no key is set, the skill now uses the
        # offline audio-metadata fallback rather than raising.
        # The fallback reports ok=False with a clear note.
        big = b"\x00" * (MAX_BYTES + 1)
        result = transcribe(big)
        assert result.get("ok") is False
        assert result.get("fallback") is True
        assert "OPENAI_API_KEY" in result.get("fallback_reason", "")

    def test_oversize_path_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-for-tests")
        p = tmp_path / "huge.ogg"
        p.write_bytes(b"fake")
        with patch.object(mod, "MAX_BYTES", 4):
            with pytest.raises(TranscribeError, match="too large|File not found|Unsupported|OPENAI_API_KEY"):
                transcribe(str(p))


class TestApiKey:
    def test_missing_key_falls_back_offline(self, monkeypatch):
        # 2026-08-03: when no key is set, the skill now uses the
        # offline audio-metadata fallback rather than raising.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        result = transcribe("https://example.com/clip.ogg")
        # The fallback returns ok=False with a clear note about
        # why transcription is unavailable.
        assert result.get("ok") is False
        assert result.get("fallback") is True
        assert "OPENAI_API_KEY" in result.get("fallback_reason", "")


class TestFormatCard:
    def test_basic(self):
        result = {
            "text": "hello world",
            "language": "en",
            "duration": 1.5,
            "elapsed": 0.4,
            "model": "whisper-1",
        }
        out = format_card(result)
        assert "Transcription" in out
        assert "EN" in out  # language uppercased
        assert "whisper-1" in out
        assert "hello world" in out

    def test_truncation(self):
        long_text = "x" * 5000
        result = {
            "text": long_text,
            "language": "ar",
            "duration": 60.0,
            "elapsed": 1.2,
            "model": "whisper-1",
        }
        out = format_card(result, max_chars=200)
        assert "truncated" in out
        assert len(out) < 600

    def test_unknown_language_marker(self):
        result = {
            "text": "hi",
            "language": "",
            "duration": 0,
            "elapsed": 0,
            "model": "whisper-1",
        }
        out = format_card(result)
        assert "?" in out  # language shows as ?


class TestFriendlyErrorMapping:
    """Make sure common API errors land on a one-line user-friendly message."""

    @pytest.mark.parametrize(
        "raw,expected_substr",
        [
            ("Incorrect API key provided: sk-***", "invalid or revoked"),
            ("You exceeded your current quota", "quota"),
            ("Rate limit reached for requests", "rate-limited"),
            ("audio_too_long: max 25 MB", "too long"),
            ("Connection error: HTTPSConnectionPool", "Network"),
            ("Request timed out", "timed out"),
        ],
    )
    def test_mapping(self, raw, expected_substr):
        out = mod._friendly_api_error(raw)
        assert expected_substr.lower() in out.lower()


class TestSupportedExts:
    def test_includes_telegram_voice(self):
        assert ".ogg" in SUPPORTED_EXTS
        assert ".oga" in SUPPORTED_EXTS

    def test_includes_common_audio(self):
        for ext in (".mp3", ".wav", ".m4a", ".webm", ".flac"):
            assert ext in SUPPORTED_EXTS


# ----------------------------------------------------------------------
# Integration test (real API)
# ----------------------------------------------------------------------
def _looks_like_real_key(k: str) -> bool:
    """Skip the live test if the env-provided key is clearly a placeholder."""
    if not k:
        return False
    bad_markers = ("test", "fake", "dummy", "placeholder", "your-key", "xxxxx")
    low = k.lower()
    if any(m in low for m in bad_markers):
        return False
    # Real OpenAI keys are 40+ chars and start with sk- or sk-proj-.
    if not (k.startswith("sk-") or k.startswith("sk-proj-")):
        return False
    if len(k) < 40:
        return False
    return True


@pytest.mark.skipif(
    not _looks_like_real_key(os.getenv("OPENAI_API_KEY", "")),
    reason="OPENAI_API_KEY missing or looks like a placeholder; "
           "skipping live Whisper call",
)
def test_live_whisper_short_audio():
    """Synthesize a 1-second silent wav in memory and send it.

    Whisper is good enough to transcribe silence to either "" or a
    no-speech token; we just want to confirm the round-trip works.
    """
    import wave

    # 1s mono 16-bit PCM silence @ 16kHz
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        with wave.open(f, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 16000)
        path = f.name

    try:
        result = transcribe(path, timeout=30.0)
        assert isinstance(result, dict)
        assert "text" in result
        assert "language" in result
        assert "duration" in result
        assert result["model"] == "whisper-1"
    finally:
        os.unlink(path)
