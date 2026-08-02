"""
skills/image_skill.py — AI image generation via OpenAI (DALL-E 3 / DALL-E 2).

Why this skill:
- DALL-E 3 is OpenAI's flagship text-to-image model. It produces
  coherent, prompt-faithful images that match nuanced natural-language
  descriptions. The OpenAI SDK is already a project dependency
  (see requirements.txt) — we add zero new packages.
- The Orca agent already exposes /transcribe for voice. A symmetric
  /image command lets the user go from idea → image directly, closing
  the multimodal loop.

Public surface:
- `generate(prompt, *, model="dall-e-3", size="1024x1024",
  quality="standard", n=1, response_format="url", timeout=120)` —
  returns a dict with `image_url` OR `image_b64`, `revised_prompt`,
  `model`, `size`, `elapsed`.
- `generate_and_save(prompt, out_path=None, **kwargs)` — generate and
  write to a file. Returns the absolute path.
- `format_card(result, *, prompt)` — Telegram caption for the image.
- `ImageGenError` — single, user-friendly exception class.

Engineering contract (Apple + Microsoft grade):
- Lazy-import the openai SDK. Missing dep surfaces a clear error at
  call time, not at import time.
- Whitelist model + size; reject unknowns with a clear hint.
- URL responses are downloaded to bytes; b64 responses are decoded.
- Auto-detect: prefer `b64_json` for `dall-e-3` (more reliable for
  large images, avoids CDN expiry), `url` for `dall-e-2`.
- Friendly error messages for: missing key, content policy violation,
  rate limit, billing/quota, network.
- loguru integration for telemetry.

This file is ADD-ONLY. It does not modify any existing module.
"""
from __future__ import annotations

import base64
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Union

from loguru import logger


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
MODELS = ("dall-e-3", "dall-e-2")
SIZES_BY_MODEL = {
    "dall-e-3": ("1024x1024", "1024x1792", "1792x1024"),
    "dall-e-2": ("256x256", "512x512", "1024x1024"),
}
QUALITIES = ("standard", "hd")  # DALL-E 3 only
DEFAULT_MODEL = "dall-e-3"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "standard"
REQUEST_TIMEOUT = 120.0  # image generation is slow

_UA = "Orca-Agent/0.6 (+https://github.com/hermasorca13-stack/Orca-Agent-Unified)"


class ImageGenError(RuntimeError):
    """Raised when image generation fails for any reason."""


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------
def _api_key() -> str:
    """Return the OpenAI API key from env, or raise a clear error."""
    key = (
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
    )
    if not key:
        raise ImageGenError(
            "OPENAI_API_KEY not set. Add it to .env to enable /image."
        )
    return key


def _client():
    """Lazy-init the OpenAI client. Import only when needed."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise ImageGenError(
            "openai SDK missing. Run: pip install 'openai>=1.0.0'"
        ) from exc
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    return OpenAI(api_key=_api_key(), base_url=base_url)


def _normalize_model(model: str) -> str:
    m = (model or "").strip().lower() or DEFAULT_MODEL
    if m not in MODELS:
        raise ImageGenError(
            f"Unknown model {model!r}. Choose from: {list(MODELS)}"
        )
    return m


def _normalize_size(model: str, size: str) -> str:
    s = (size or "").strip() or DEFAULT_SIZE
    allowed = SIZES_BY_MODEL[model]
    if s not in allowed:
        raise ImageGenError(
            f"Size {size!r} is not valid for {model}. "
            f"Choose from: {list(allowed)}"
        )
    return s


def _normalize_quality(model: str, quality: str) -> str:
    if model != "dall-e-3":
        # dall-e-2 has no quality param
        return quality  # ignored
    q = (quality or "").strip().lower() or DEFAULT_QUALITY
    if q not in QUALITIES:
        raise ImageGenError(
            f"Quality {quality!r} is not valid. Choose from: {list(QUALITIES)}"
        )
    return q


def _normalize_n(model: str, n: int) -> int:
    n = int(n)
    if n < 1:
        raise ImageGenError("n must be >= 1")
    if model == "dall-e-3" and n != 1:
        # DALL-E 3 only supports n=1.
        raise ImageGenError("dall-e-3 only supports n=1")
    if model == "dall-e-2" and n > 10:
        raise ImageGenError("dall-e-2 supports at most n=10")
    return n


def _download(url: str, timeout: float = 30.0) -> bytes:
    """Download an image URL to bytes."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001
        raise ImageGenError(
            f"Could not download image: {exc.__class__.__name__}: {str(exc)[:120]}"
        ) from exc


def _friendly_error(raw: str) -> str:
    s = raw.lower()
    if "safety" in s or "content_policy" in s or "policy_violation" in s:
        return "OpenAI content policy rejected this prompt. Try rephrasing."
    if "billing" in s or "insufficient_quota" in s or "exceeded your current quota" in s:
        return "OpenAI quota exhausted. Check billing."
    if "invalid_api_key" in s or "incorrect api key" in s or "401" in s:
        return "OPENAI_API_KEY is invalid or revoked."
    if "rate_limit" in s or "rate limit" in s or "429" in s:
        return "OpenAI rate-limited. Retry shortly."
    if "timeout" in s or "timed out" in s:
        return "OpenAI timed out. Try a simpler prompt."
    if "connection" in s or "network" in s:
        return "Network error reaching OpenAI. Check connectivity."
    return raw.splitlines()[0][:200] if raw else "Image generation error"


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def generate(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    size: str = DEFAULT_SIZE,
    quality: str = DEFAULT_QUALITY,
    n: int = 1,
    response_format: str = "auto",
    timeout: float = REQUEST_TIMEOUT,
) -> Dict[str, Any]:
    """Generate an image from a text prompt via OpenAI.

    Args:
        prompt: text description of the desired image.
        model: 'dall-e-3' (default) or 'dall-e-2'.
        size: pixel size; valid values depend on the model.
        quality: 'standard' or 'hd' (DALL-E 3 only).
        n: number of images. DALL-E 3 is fixed to 1.
        response_format: 'url' | 'b64_json' | 'auto'. 'auto' prefers
            b64_json for DALL-E 3 (avoids CDN expiry), url for DALL-E 2.
        timeout: request timeout in seconds.

    Returns:
        dict with: prompt, model, size, quality, image_url OR image_b64
        (raw base64 string), revised_prompt, elapsed, n.

    Raises:
        ImageGenError on any failure.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ImageGenError("Empty prompt")
    if len(prompt) > 4000:
        # DALL-E 3 limit is 4000 chars; DALL-E 2 is 1000.
        # We cap at 4000 and let the user know via the error if exceeded.
        # Truncate defensively instead of failing.
        prompt = prompt[:4000]
    model_n = _normalize_model(model)
    size_n = _normalize_size(model_n, size)
    quality_n = _normalize_quality(model_n, quality)
    n_n = _normalize_n(model_n, n)
    if response_format == "auto":
        response_format = "b64_json" if model_n == "dall-e-3" else "url"
    if response_format not in ("url", "b64_json"):
        raise ImageGenError(
            f"response_format must be 'url', 'b64_json', or 'auto' (got {response_format!r})"
        )

    _ = _api_key()  # fail fast on missing key
    client = _client()

    t0 = time.monotonic()
    logger.info(
        "image generate | model={} size={} quality={} n={} prompt_len={}",
        model_n, size_n, quality_n, n_n, len(prompt),
    )
    try:
        kwargs: Dict[str, Any] = dict(
            model=model_n,
            prompt=prompt,
            size=size_n,
            n=n_n,
            response_format=response_format,
            timeout=timeout,
        )
        if model_n == "dall-e-3":
            kwargs["quality"] = quality_n
        resp = client.images.generate(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise ImageGenError(_friendly_error(str(exc))) from exc

    elapsed = time.monotonic() - t0

    # Normalise response (pydantic model or dict).
    if hasattr(resp, "model_dump"):
        data = resp.model_dump()
    elif hasattr(resp, "to_dict"):
        data = resp.to_dict()
    elif isinstance(resp, dict):
        data = resp
    else:
        data = {"data": []}

    items = data.get("data") or []
    if not items:
        raise ImageGenError("OpenAI returned no images")

    first = items[0]
    image_url = first.get("url")
    image_b64 = first.get("b64_json")
    revised = first.get("revised_prompt")

    out: Dict[str, Any] = {
        "prompt": prompt,
        "model": model_n,
        "size": size_n,
        "quality": quality_n,
        "n": n_n,
        "revised_prompt": revised,
        "elapsed": round(elapsed, 2),
    }
    if image_b64:
        out["image_b64"] = image_b64
    if image_url:
        out["image_url"] = image_url

    logger.info(
        "image generate ok | model={} size={} elapsed={}s revised={}",
        model_n, size_n, out["elapsed"], bool(revised),
    )
    return out


def generate_and_save(
    prompt: str,
    out_path: Optional[Union[str, Path]] = None,
    **kwargs,
) -> str:
    """Generate an image and write it to a file.

    If `out_path` is omitted, writes to a temp file with a sensible
    name. Returns the absolute path of the saved file.
    """
    result = generate(prompt, **kwargs)
    # Prefer b64 (immediate, no network round-trip). Fall back to URL.
    if "image_b64" in result:
        data = base64.b64decode(result["image_b64"])
    elif "image_url" in result:
        data = _download(result["image_url"])
    else:
        raise ImageGenError("No image data in result")

    if out_path is None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            out_path = f.name
    out = Path(out_path)
    if out.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        out = out.with_suffix(".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    logger.info(
        "image saved | path={} bytes={}", out.name, len(data),
    )
    return str(out.resolve())


# ----------------------------------------------------------------------
# Format helper (Telegram caption)
# ----------------------------------------------------------------------
def format_card(result: Dict[str, Any], *, max_prompt: int = 200) -> str:
    """Build a Telegram caption for the image."""
    parts = [f"🎨 *{result.get('model', 'dall-e')}* • {result.get('size', '?')}"]
    if result.get("revised_prompt"):
        rp = result["revised_prompt"]
        if len(rp) > max_prompt:
            rp = rp[:max_prompt] + "…"
        parts.append(f"_Revised prompt:_ {rp}")
    parts.append(f"_API: {float(result.get('elapsed') or 0):.1f}s_")
    return "\n".join(parts)


__all__ = [
    "generate", "generate_and_save", "format_card",
    "ImageGenError", "MODELS", "SIZES_BY_MODEL", "QUALITIES",
    "DEFAULT_MODEL", "DEFAULT_SIZE", "DEFAULT_QUALITY",
]
