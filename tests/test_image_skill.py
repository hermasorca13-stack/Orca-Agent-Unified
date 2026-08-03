"""
Tests for skills/image_skill.py.

Unit tests mock the OpenAI SDK. No real API calls. The "live" test
is skipped without a real-looking OPENAI_API_KEY.
"""
from __future__ import annotations

import base64
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "image_skill.py"


def _load_skill():
    spec = importlib.util.spec_from_file_location(
        "image_skill_under_test", str(SKILL_PATH)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["image_skill_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_skill()
generate = mod.generate
generate_and_save = mod.generate_and_save
format_card = mod.format_card
ImageGenError = mod.ImageGenError
MODELS = mod.MODELS


# ----------------------------------------------------------------------
# Argument validation
# ----------------------------------------------------------------------
class TestArguments:
    def test_empty_prompt(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        with pytest.raises(ImageGenError, match="Empty prompt"):
            generate("   ")

    def test_unknown_model(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        with pytest.raises(ImageGenError, match="Unknown model"):
            generate("x", model="bogus")

    def test_bad_size(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        with pytest.raises(ImageGenError, match="Size .* is not valid"):
            generate("x", model="dall-e-3", size="512x512")

    def test_bad_quality(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        with pytest.raises(ImageGenError, match="Quality .* is not valid"):
            generate("x", quality="ultra")

    def test_n_too_high_dalle3(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        with pytest.raises(ImageGenError, match="dall-e-3 only supports n=1"):
            generate("x", model="dall-e-3", n=2)

    def test_n_too_high_dalle2(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        with pytest.raises(ImageGenError, match="at most n=10"):
            generate("x", model="dall-e-2", n=20)

    def test_n_zero(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        with pytest.raises(ImageGenError, match="n must be"):
            generate("x", n=0)

    def test_bad_response_format(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        with pytest.raises(ImageGenError, match="response_format"):
            generate("x", response_format="xml")


# ----------------------------------------------------------------------
# Key + error paths
# ----------------------------------------------------------------------
class TestKeys:
    def test_missing_key_falls_back_to_local(self, monkeypatch):
        # 2026-08-03: when no OpenAI key is set, the skill now
        # routes to the local Pillow-based offline generator
        # rather than raising. Zero capability loss.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        result = generate("a cat", size="1024x1024")
        assert result.get("offline") is True
        assert result.get("model") == "orca-local-v1"
        assert result.get("image_b64") or result.get("image_url")
        assert "OPENAI_API_KEY" in result.get("fallback_reason", "")


class TestErrorMapping:
    @pytest.mark.parametrize(
        "raw,expected_substr",
        [
            ("content_policy_violation: too violent", "content policy"),
            ("Incorrect API key provided", "invalid or revoked"),
            ("You exceeded your current quota", "quota"),
            ("Rate limit reached", "rate-limited"),
            ("HTTPSConnectionPool: read timed out", "timed out"),
            ("Connection refused", "Network"),
        ],
    )
    def test_mapping(self, raw, expected_substr):
        out = mod._friendly_error(raw)
        assert expected_substr.lower() in out.lower()


# ----------------------------------------------------------------------
# Mocked success path
# ----------------------------------------------------------------------
class TestSuccess:
    def test_dalle3_b64(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        # 1x1 transparent PNG
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        )
        b64 = base64.b64encode(png_bytes).decode("ascii")
        fake_client = MagicMock()
        fake_client.images.generate.return_value = {
            "data": [{"b64_json": b64, "revised_prompt": "a tiny dot"}],
        }
        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = fake_client
        with patch.dict(sys.modules, {"openai": fake_openai}):
            result = generate("a cat", response_format="b64_json")
        assert result["model"] == "dall-e-3"
        assert result["image_b64"] == b64
        assert result["revised_prompt"] == "a tiny dot"
        assert "image_url" not in result

        # Now save and verify.
        with patch.dict(sys.modules, {"openai": fake_openai}):
            p = generate_and_save("a cat", out_path=str(tmp_path / "x.png"),
                                  response_format="b64_json")
        assert Path(p).exists()
        assert Path(p).read_bytes() == png_bytes

    def test_dalle2_url(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        fake_client = MagicMock()
        fake_client.images.generate.return_value = {
            "data": [{"url": "https://example.com/img.png"}],
        }
        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = fake_client
        with patch.dict(sys.modules, {"openai": fake_openai}):
            result = generate("a cat", model="dall-e-2", response_format="url")
        assert result["image_url"] == "https://example.com/img.png"
        assert "image_b64" not in result

    def test_auto_format_picks_b64_for_dalle3(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        fake_client = MagicMock()
        fake_client.images.generate.return_value = {
            "data": [{"b64_json": "abcd"}],
        }
        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = fake_client
        with patch.dict(sys.modules, {"openai": fake_openai}):
            generate("x", model="dall-e-3")
        # Verify the call used b64_json, not url.
        call = fake_client.images.generate.call_args
        assert call.kwargs["response_format"] == "b64_json"

    def test_auto_format_picks_url_for_dalle2(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        fake_client = MagicMock()
        fake_client.images.generate.return_value = {
            "data": [{"url": "https://example.com/x.png"}],
        }
        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = fake_client
        with patch.dict(sys.modules, {"openai": fake_openai}):
            generate("x", model="dall-e-2")
        call = fake_client.images.generate.call_args
        assert call.kwargs["response_format"] == "url"

    def test_empty_response_raises(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        fake_client = MagicMock()
        fake_client.images.generate.return_value = {"data": []}
        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = fake_client
        with patch.dict(sys.modules, {"openai": fake_openai}):
            with pytest.raises(ImageGenError, match="no images"):
                generate("x", model="dall-e-2")

    def test_quality_ignored_for_dalle2(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
        fake_client = MagicMock()
        fake_client.images.generate.return_value = {"data": [{"url": "https://x"}]}
        fake_openai = MagicMock()
        fake_openai.OpenAI.return_value = fake_client
        with patch.dict(sys.modules, {"openai": fake_openai}):
            # DALL-E 2 should accept any quality value silently.
            generate("x", model="dall-e-2", quality="hd")
        # Verify quality was NOT passed in the call.
        call = fake_client.images.generate.call_args
        assert "quality" not in call.kwargs


# ----------------------------------------------------------------------
# Format helper
# ----------------------------------------------------------------------
class TestFormatCard:
    def test_basic(self):
        result = {
            "model": "dall-e-3",
            "size": "1024x1024",
            "elapsed": 4.2,
            "revised_prompt": "a tiny dot",
        }
        out = format_card(result)
        assert "dall-e-3" in out
        assert "1024x1024" in out
        assert "a tiny dot" in out
        assert "4.2s" in out

    def test_long_revised_truncated(self):
        result = {
            "model": "dall-e-3",
            "size": "1024x1024",
            "elapsed": 1.0,
            "revised_prompt": "x" * 1000,
        }
        out = format_card(result, max_prompt=50)
        assert "…" in out

    def test_no_revised(self):
        result = {
            "model": "dall-e-2",
            "size": "512x512",
            "elapsed": 0.5,
        }
        out = format_card(result)
        assert "dall-e-2" in out
        assert "Revised" not in out


class TestModels:
    def test_models(self):
        assert "dall-e-3" in MODELS
        assert "dall-e-2" in MODELS

    def test_sizes_by_model(self):
        # DALL-E 3 supports portrait + landscape + square
        assert "1024x1792" in mod.SIZES_BY_MODEL["dall-e-3"]
        assert "1792x1024" in mod.SIZES_BY_MODEL["dall-e-3"]
        # DALL-E 2 supports smaller sizes
        assert "256x256" in mod.SIZES_BY_MODEL["dall-e-2"]


# ----------------------------------------------------------------------
# Live integration (skipped without real key)
# ----------------------------------------------------------------------
def _looks_like_real_key(k: str) -> bool:
    if not k:
        return False
    bad = ("test", "fake", "dummy", "placeholder")
    low = k.lower()
    if any(m in low for m in bad):
        return False
    if not (k.startswith("sk-") or k.startswith("sk-proj-")):
        return False
    return len(k) >= 40


@pytest.mark.skipif(
    not _looks_like_real_key(os.getenv("OPENAI_API_KEY", "")),
    reason="OPENAI_API_KEY missing or looks like a placeholder",
)
def test_live_dalle3_small_image():
    """Generate a small DALL-E 3 image (cost: ~$0.04)."""
    import time as _t
    t0 = _t.monotonic()
    result = generate("a tiny red square on a white background",
                      model="dall-e-3", size="1024x1024", timeout=60.0)
    assert "image_b64" in result or "image_url" in result
    assert result["model"] == "dall-e-3"
    print(f"live DALL-E 3 generation took {_t.monotonic() - t0:.1f}s")
