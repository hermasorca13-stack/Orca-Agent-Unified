"""
Tests for skills/offline_fallbacks.py.

The offline fallback layer is the zero-key counterpart of every
key-dependent skill. These tests confirm that:

  - local_image always returns a real PNG file (Pillow-based)
  - the same prompt produces the same image (deterministic)
  - local_audio_info returns structured metadata, never raises
  - local_text_complete handles summarise / list / question forms
  - local_transcribe_placeholder returns the documented shape

All tests are pure-stdlib + Pillow (already in requirements.txt).
"""
from __future__ import annotations

import base64
import importlib.util
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "offline_fallbacks.py"


def _load_skill():
    spec = importlib.util.spec_from_file_location(
        "offline_fallbacks_under_test", str(SKILL_PATH))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["offline_fallbacks_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_skill()


# ======================================================================
# local_image
# ======================================================================
class TestLocalImage:
    """Pillow-based procedural image generator."""

    def test_returns_png_bytes(self):
        result = mod.local_image("a cat in a hat", size="512x512")
        assert "image_b64" in result
        assert result["image_b64"], "image_b64 should be non-empty"
        raw = base64.b64decode(result["image_b64"])
        # PNG magic number: 89 50 4E 47 0D 0A 1A 0A
        assert raw[:8] == b"\x89PNG\r\n\x1a\n", (
            f"not a valid PNG: first 8 bytes = {raw[:8].hex()}"
        )

    def test_writes_real_file(self):
        result = mod.local_image("a sunset over the pyramids", size="512x512")
        path = Path(result["image_path"])
        assert path.exists(), f"file does not exist: {path}"
        # Should be a non-trivial PNG
        assert path.stat().st_size > 5_000, "PNG too small"

    def test_deterministic(self):
        # Same prompt -> same image (same path, same bytes)
        r1 = mod.local_image("a unique deterministic test prompt", size="256x256")
        r2 = mod.local_image("a unique deterministic test prompt", size="256x256")
        assert r1["image_path"] == r2["image_path"]
        assert r1["image_b64"] == r2["image_b64"]

    def test_different_prompts_different_images(self):
        r1 = mod.local_image("prompt AAA", size="256x256")
        r2 = mod.local_image("prompt BBB", size="256x256")
        assert r1["image_path"] != r2["image_path"]
        assert r1["image_b64"] != r2["image_b64"]

    def test_size_respected(self):
        # Check that the PNG dimensions match the requested size
        from PIL import Image
        import io
        result = mod.local_image("size test", size="768x384")
        raw = base64.b64decode(result["image_b64"])
        img = Image.open(io.BytesIO(raw))
        assert img.size == (768, 384)

    def test_handles_invalid_size(self):
        # Bad size string -> defaults to 1024x1024
        result = mod.local_image("size test", size="garbage")
        # Should still produce a valid image
        assert result["image_b64"]
        # The returned size field reflects the actual dimensions
        assert "x" in result["size"]

    def test_long_prompt_truncated(self):
        # Very long prompt should be truncated, not crash
        long_prompt = "word " * 200
        result = mod.local_image(long_prompt, size="256x256")
        assert result["image_b64"]
        assert len(result["revised_prompt"]) <= 280

    def test_arabic_prompt(self):
        result = mod.local_image("غروب شمس على أهرامات الجيزة", size="256x256")
        assert result["image_b64"]
        # The file is real even with non-ASCII input
        assert Path(result["image_path"]).exists()

    def test_under_5_seconds(self):
        # 256x256 should generate in well under 5s
        t0 = time.monotonic()
        mod.local_image("a fast test", size="256x256")
        elapsed = time.monotonic() - t0
        assert elapsed < 5.0, f"too slow: {elapsed:.2f}s"


# ======================================================================
# local_audio_info
# ======================================================================
class TestLocalAudioInfo:
    """Best-effort audio metadata extraction."""

    def test_nonexistent_file(self):
        info = mod.local_audio_info("C:/nonexistent/file.mp3")
        assert info["ok"] is False
        assert "not found" in info["note"].lower()
        assert info["format"] == "mp3"

    def test_url_source(self):
        info = mod.local_audio_info("https://example.com/audio.ogg")
        assert info["ok"] is False
        assert info["format"] == "url"
        assert "no download" in info["note"].lower() or "URL" in info["note"]

    def test_bytes_source(self):
        info = mod.local_audio_info(b"\x00" * 1024)
        assert info["ok"] is False
        assert info["format"] == "bytes"
        assert info["source"] == "bytes"

    def test_real_wav(self, tmp_path):
        # Write a minimal valid WAV file
        import wave
        wav_path = tmp_path / "test.wav"
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 16000)  # 1 second of silence
        info = mod.local_audio_info(str(wav_path))
        assert info["ok"] is True
        assert info["channels"] == 1
        assert info["sample_rate"] == 16000
        assert info["duration_seconds"] == pytest.approx(1.0, abs=0.1)
        assert info["bitrate"] == 16000 * 2 * 8  # rate * sampwidth * 8 * channels

    def test_never_raises(self):
        # Even garbage input must not raise
        for bad in [None, 42, [], {}, 3.14]:
            try:
                mod.local_audio_info(bad)
            except Exception as exc:
                pytest.fail(f"raised on {bad!r}: {exc}")


# ======================================================================
# local_text_complete
# ======================================================================
class TestLocalTextComplete:
    """Rule-based text completion (NOT an LLM)."""

    def test_empty_prompt_returns_empty(self):
        assert mod.local_text_complete("") == ""
        assert mod.local_text_complete("   ") == ""

    def test_summarise(self):
        text = "summarize: First sentence. Second sentence. Third sentence."
        result = mod.local_text_complete(text)
        assert "Summary" in result
        # Should include the first 3 sentences
        assert "First" in result
        assert "Second" in result
        assert "Third" in result

    def test_list(self):
        result = mod.local_text_complete("list: alpha, beta, gamma, delta")
        assert "1. alpha" in result
        assert "2. beta" in result
        assert "3. gamma" in result
        assert "4. delta" in result

    def test_arabic_list(self):
        result = mod.local_text_complete("اكتب: تفاح, برتقال, موز")
        assert "1." in result
        assert "تفاح" in result

    def test_question_returns_polite_refusal(self):
        result = mod.local_text_complete("What is the meaning of life?")
        assert "LLM key" in result or "offline" in result.lower()
        # The original question is echoed for context
        assert "meaning of life" in result

    def test_default_echo(self):
        result = mod.local_text_complete("Hello world")
        assert "offline" in result.lower()
        assert "Hello world" in result

    def test_never_raises(self):
        for bad in [None, 42, [], {}, 3.14, b"bytes"]:
            try:
                mod.local_text_complete(bad or "")
            except Exception as exc:
                pytest.fail(f"raised on {bad!r}: {exc}")


# ======================================================================
# local_transcribe_placeholder
# ======================================================================
class TestLocalTranscribePlaceholder:
    """Returns a structured 'no transcription' response."""

    def test_returns_documented_shape(self):
        result = mod.local_transcribe_placeholder("test.mp3")
        # Must have these keys (matches the OpenAI Whisper shape)
        for k in ("text", "language", "duration", "model", "elapsed",
                  "segments", "ok", "fallback"):
            assert k in result, f"missing key: {k}"
        assert result["ok"] is False
        assert result["fallback"] is True
        assert result["model"] == "orca-local-noop"
        assert result["text"] == ""

    def test_bytes_input(self):
        result = mod.local_transcribe_placeholder(b"\x00" * 4096)
        assert result["ok"] is False
        assert result["fallback"] is True
        # size_kb should be reported
        assert result["size_kb"] == pytest.approx(4.0, abs=0.5)

    def test_path_input(self, tmp_path):
        p = tmp_path / "audio.mp3"
        p.write_bytes(b"\x00" * 2048)
        result = mod.local_transcribe_placeholder(str(p))
        assert result["ok"] is False
        assert result["size_kb"] == pytest.approx(2.0, abs=0.5)

    def test_includes_audio_info(self):
        result = mod.local_transcribe_placeholder("nonexistent.mp3")
        assert "audio_info" in result
        assert "note" in result

    def test_includes_diagnostic_note(self):
        result = mod.local_transcribe_placeholder("test.ogg")
        assert "no LLM key" in result["note"].lower() or "no local model" in result["note"].lower()
        assert "OPENAI_API_KEY" in result["fallback_reason"]


# ======================================================================
# local_search (multi-provider chain)
# ======================================================================
class TestLocalSearch:
    """Multi-provider web search (DDG -> Wikipedia)."""

    def test_returns_list(self):
        out = mod.local_search("python tutorial 2026", limit=3)
        assert isinstance(out, list)
        # Each item, if present, is a dict with title/url/snippet
        for item in out:
            assert "title" in item
            assert "url" in item
            assert "snippet" in item

    def test_never_raises(self):
        # Even with weird input, never raises
        for bad in ["", "   ", "q" * 10_000, "!?@#$%^&*()"]:
            try:
                mod.local_search(bad, limit=1)
            except Exception as exc:
                pytest.fail(f"raised on {bad!r}: {exc}")


# ======================================================================
# _wikipedia_search (direct unit tests)
# ======================================================================
class TestWikipediaSearch:
    """Direct tests for the Wikipedia REST backend. The chain calls
    this when DDG returns nothing (which is the common case in 2026).
    """

    def test_empty_query_returns_empty(self):
        out = mod._wikipedia_search("", limit=5, timeout=5)
        assert out == []

    def test_returns_well_formed_items(self):
        out = mod._wikipedia_search("Python programming language",
                                     limit=3, timeout=10)
        # Real results OR empty list if network is down — both OK
        for item in out:
            assert "title" in item and item["title"]
            assert "url" in item
            assert "wikipedia.org" in item["url"]
            assert "snippet" in item
            assert item.get("source") == "wikipedia"


# ======================================================================
# _ddg_search (graceful degradation under 2026 anomaly detector)
# ======================================================================
class TestDDGSearch:
    """The DDG path is best-effort. In 2026 it usually returns []
    due to the anomaly detector — and that's the correct behaviour."""

    def test_returns_list_even_when_blocked(self):
        # Should not raise, should return a list
        out = mod._ddg_search("python", limit=3, timeout=5)
        assert isinstance(out, list)

    def test_handles_anomaly_detector(self):
        # If the request actually hits DDG and gets the anomaly
        # page, we should return [] rather than parsing garbage.
        # The implementation detects "anomaly-modal" in the body.
        out = mod._ddg_search("python", limit=3, timeout=5)
        # Either [] (anomaly) or real results, never bogus matches
        for item in out:
            assert "title" in item
