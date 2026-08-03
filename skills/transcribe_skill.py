"""
skills/transcribe_skill.py — Audio transcription via OpenAI Whisper API.

Why this skill:
- Voice is the primary input on Telegram (the user sends voice notes
  constantly per MASTER_PROMPT). Turning voice into text unlocks every
  downstream skill (summarize, translate, search, save, LLM routing).
- OpenAI's `whisper-1` model via the official API is the most reliable
  route in 2026: 99 languages, no model download, no GPU required,
  ~$0.006 / minute. The `openai` SDK is already a project dependency
  (see requirements.txt), so we add zero new packages.

Public surface:
- `transcribe(source, *, language=None, prompt=None, timeout=60)` —
  accepts a local file path, an http(s) URL, or raw audio bytes.
  Returns a dict with `text`, `language`, `duration`, `model`,
  `elapsed`, and `segments`.
- `format_card(result)` — Markdown-friendly summary for Telegram.
- `TranscribeError` — single, user-friendly exception class.

Engineering contract (Apple + Microsoft grade):
- Lazy-init the OpenAI client. Missing `openai` SDK surfaces a clear
  error at call time, not at import time.
- Whitelist file extensions (.ogg, .mp3, .wav, .m4a, .webm, .mp4,
  .mpeg, .mpga, .flac). Anything else fails fast with a friendly
  message.
- Enforce the 25 MB hard limit that OpenAI imposes. Refuse early.
- Map common API errors (quota, rate-limit, bad key, file size,
  timeout) to one-line, user-readable messages.
- loguru integration for telemetry (chars, language, duration, API
  elapsed seconds).
- No global state; every call constructs a fresh client from env.

This file is ADD-ONLY. It does not modify any existing module.
"""
from __future__ import annotations

import os
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
# OpenAI Whisper API hard limit.
MAX_BYTES = 25 * 1024 * 1024

# File extensions we accept. Whisper accepts more, but we whitelist
# to keep user input predictable and to fail fast on garbage.
SUPPORTED_EXTS = {
    ".ogg", ".oga",  # Telegram voice notes arrive as .ogg
    ".mp3", ".wav", ".m4a", ".webm",
    ".mp4", ".mpeg", ".mpga", ".flac",
}

_UA = "Orca-Agent/0.6 (+https://github.com/hermasorca13-stack/Orca-Agent-Unified)"


class TranscribeError(RuntimeError):
    """Raised when transcription fails for any reason."""


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------
def _api_key() -> str:
    """Return the OpenAI API key from env, or empty string.

    We prefer `OPENAI_API_KEY` because Whisper is OpenAI-specific.
    Falls back to `LLM_API_KEY` so existing single-key setups work.

    When no key is set, returns "" so the public API can branch
    into the offline fallback. We do NOT raise here; the public
    API is the single switch between the two paths.
    """
    key = (
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
    )
    return key


def _model() -> str:
    return os.getenv("ORCA_TRANSCRIBE_MODEL", "whisper-1").strip() or "whisper-1"


def _client():
    """Lazy-init the OpenAI client. Import only when needed."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise TranscribeError(
            "openai SDK missing. Run: pip install 'openai>=1.0.0'"
        ) from exc
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
    return OpenAI(api_key=_api_key(), base_url=base_url)


def _kind_of(source: Any) -> str:
    if isinstance(source, (bytes, bytearray, memoryview)):
        return "bytes"
    s = str(source)
    if s.startswith(("http://", "https://")):
        return "url"
    return "path"


def _download(url: str, timeout: float = 30.0) -> bytes:
    """Download a URL to bytes. Wraps any network error in TranscribeError."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except Exception as exc:  # noqa: BLE001
        raise TranscribeError(
            f"Could not download audio: {exc.__class__.__name__}: {exc}".splitlines()[0][:200]
        ) from exc
    if len(data) > MAX_BYTES:
        raise TranscribeError(
            f"Audio too large after download: {len(data) / 1024 / 1024:.1f} MB "
            f"(max 25 MB). Trim or compress before sending."
        )
    return data


def _resolve_source(source: Union[str, bytes, Path, bytearray, memoryview]):
    """Normalise any accepted input into (bytes, filename)."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        # Caller passed raw audio. Default to .ogg because that is the
        # format Telegram voice notes arrive in. Callers can override
        # by transcribing a file path instead.
        return bytes(source), "audio.ogg"

    s = str(source)
    if s.startswith(("http://", "https://")):
        data = _download(s)
        path = urllib.parse.urlparse(s).path
        fname = Path(path).name or "audio.ogg"
        if Path(fname).suffix.lower() not in SUPPORTED_EXTS:
            fname = f"{fname or 'audio'}.ogg"
        return data, fname

    # Treat as a local file path.
    path = Path(s)
    if not path.exists():
        raise TranscribeError(f"File not found: {path}")
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise TranscribeError(
            f"Unsupported extension {ext!r}. Supported: {sorted(SUPPORTED_EXTS)}"
        )
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise TranscribeError(
            f"File too large: {len(data) / 1024 / 1024:.1f} MB (max 25 MB)."
        )
    return data, path.name


def _call_whisper(
    audio_bytes: bytes,
    filename: str,
    *,
    language: Optional[str],
    prompt: Optional[str],
    timeout: float,
) -> Dict[str, Any]:
    """Call OpenAI Whisper API and return a normalised dict."""
    client = _client()

    suffix = Path(filename).suffix or ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        t0 = time.monotonic()
        with tmp_path.open("rb") as fh:
            kwargs: Dict[str, Any] = dict(
                model=_model(),
                file=(filename, fh),
                response_format="verbose_json",
                timeout=timeout,
            )
            if language:
                kwargs["language"] = language
            if prompt:
                kwargs["prompt"] = prompt
            resp = client.audio.transcriptions.create(**kwargs)
        elapsed = time.monotonic() - t0

        # Normalise response: pydantic model, dataclass, or dict.
        if hasattr(resp, "model_dump"):
            data = resp.model_dump()
        elif hasattr(resp, "to_dict"):
            data = resp.to_dict()
        elif isinstance(resp, dict):
            data = resp
        else:
            data = {"text": str(resp)}

        text = (data.get("text") or "").strip()
        if not text:
            raise TranscribeError("Whisper returned empty text")

        return {
            "text": text,
            "language": (data.get("language") or language or "unknown").lower(),
            "duration": float(data.get("duration") or 0.0),
            "model": _model(),
            "elapsed": round(elapsed, 2),
            "segments": data.get("segments") or [],
        }
    except TranscribeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TranscribeError(_friendly_api_error(str(exc))) from exc
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _friendly_api_error(raw: str) -> str:
    """Map common OpenAI error strings to a one-line user message."""
    s = raw.lower()
    if "insufficient_quota" in s or "exceeded your current quota" in s or "billing" in s and "quota" in s:
        return "OpenAI quota exhausted. Check billing."
    if "invalid_api_key" in s or "incorrect api key" in s or "401" in s:
        return "OPENAI_API_KEY is invalid or revoked."
    if "rate_limit" in s or "rate limit" in s or "429" in s:
        return "OpenAI rate-limited. Retry in a few seconds."
    if "audio_too_long" in s or "max_size" in s or "file size" in s or "25 mb" in s:
        return "Audio too long or large for Whisper API."
    if "timeout" in s or "timed out" in s:
        return "Whisper API timed out. Try a shorter clip."
    if "connection" in s or "network" in s:
        return "Network error reaching OpenAI. Check connectivity."
    return raw.splitlines()[0][:200] if raw else "Unknown transcription error"


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def transcribe(
    source: Union[str, bytes, Path, bytearray, memoryview],
    *,
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Transcribe an audio source to text via OpenAI Whisper.

    Args:
        source: file path (str/Path), http(s) URL, or raw audio bytes.
        language: optional ISO-639-1 hint (e.g. "ar", "en"). When
            omitted, Whisper auto-detects. Use this when you know the
            language to improve accuracy and latency.
        prompt: optional context hint (max 1024 chars). Useful for
            guiding the model on mixed-language clips or jargon
            ("Arabic and English mix, technical terms").
        timeout: API request timeout in seconds (default 60).

    Returns:
        dict with keys: text, language, duration, model, elapsed,
        segments (list of {start, end, text} dicts when available).

    Raises:
        TranscribeError on any failure, with a user-friendly message.
    """
    if language:
        language = language.strip().lower() or None
    if prompt:
        prompt = prompt.strip()[:1024] or None

    # When no API key is configured, route to the offline fallback
    # (audio metadata + clear note). We do NOT crash.
    if not _api_key():
        from skills.offline_fallbacks import local_transcribe_placeholder
        logger.info(
            "transcribe OFFLINE | no key; running audio metadata fallback"
        )
        return local_transcribe_placeholder(source)

    kind = _kind_of(source)
    logger.info(
        "transcribe start | kind={} language={} prompt={}",
        kind, language or "auto", "yes" if prompt else "no",
    )

    data, fname = _resolve_source(source)
    result = _call_whisper(
        data, fname, language=language, prompt=prompt, timeout=timeout,
    )
    logger.info(
        "transcribe ok | chars={} lang={} dur={}s api={}s",
        len(result["text"]), result["language"],
        result["duration"], result["elapsed"],
    )
    return result


def format_card(result: Dict[str, Any], *, max_chars: int = 3500) -> str:
    """Format a transcription result as a Telegram-friendly card.

    Truncates the text body to `max_chars` and adds a small footer
    with language, audio duration, and the API elapsed time.
    """
    text = (result.get("text") or "").strip()
    lang = (result.get("language") or "?").upper()
    dur = float(result.get("duration") or 0)
    elapsed = float(result.get("elapsed") or 0)
    model = result.get("model") or "whisper-1"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]"
    lines = [
        "🎙 *Transcription*",
        f"_Language: {lang} • Audio: {dur:.1f}s • API: {elapsed:.1f}s • Model: {model}_",
        "",
        text,
    ]
    return "\n".join(lines)


__all__ = ["transcribe", "format_card", "TranscribeError", "SUPPORTED_EXTS", "MAX_BYTES"]
