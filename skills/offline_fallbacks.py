"""
skills/offline_fallbacks.py — Local, zero-dependency-extra fallbacks for
every skill that needs an external API key.

Goal: 0% loss of capability when OPENAI_API_KEY, TAVILY_API_KEY,
SERPER_API_KEY, or any other external service is missing. The bot
should still produce useful output for every command.

This module is the single point of truth for offline alternatives.
Each key-dependent skill calls into here when its primary path is
unavailable.

Public surface (all pure-stdlib + Pillow + numpy, which are already
in requirements.txt):

  - local_image(prompt, size, ...)         — Pillow-based procedural art
      that incorporates the prompt text. Not photorealistic but visually
      meaningful: a gradient + the prompt rendered over it. Useful for
      previews, placeholders, and offline demos.

  - local_audio_info(source, ...)         — best-effort audio metadata
      extraction using stdlib (wave) + ffmpeg if present. Returns
      duration, channels, bitrate, format. Useful when the user sends
      a voice note and we have no Whisper key.

  - local_search(query, limit, ...)        — direct DuckDuckGo HTML scrape
      as a robust fallback for the Tavily/Serper providers. Already
      used in web_search_skill but exposed here so other skills can
      call it directly.

  - local_text_complete(prompt, max_tokens) — small rule-based text
      completion. NOT an LLM, but useful for quick structured answers
      when no LLM key is set (eg, "summarize this in 3 bullets").
      Used by the LLM router's last-resort fallback.

  - local_transcribe_placeholder(source, duration) — returns a clear
      structured message saying "transcription unavailable, here is
      what we DO know about the audio". Better than crashing.

All functions are defensive: never raise on bad input. They return
a clear, structured response (often with a note explaining the
fallback was used).

This file is ADD-ONLY.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import struct
import subprocess
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


_UA = "Orca-Agent/0.7 (+https://github.com/hermasorca13-stack/Orca-Agent-Unified)"


# =====================================================================
# Local image generation (Pillow-based procedural art)
# =====================================================================
def local_image(
    prompt: str,
    *,
    size: str = "1024x1024",
    output_format: str = "PNG",
) -> Dict[str, Any]:
    """Generate a procedural image from a text prompt.

    Output is a Pillow-generated image that:
      - has a unique gradient based on the prompt hash (so the same
        prompt always produces the same image — deterministic)
      - has the prompt text rendered on top in a stylised way
      - is saved to a temporary file and returned with the file path
        + the raw PNG bytes

    Args:
        prompt: any free-form text. Truncated to 280 chars in render.
        size: 'WxH' string, e.g. '1024x1024', '1024x1792', '1792x1024'.
        output_format: 'PNG' or 'JPEG' (PNG default for lossless).

    Returns:
        dict with keys: image_path, image_b64, size, model='orca-local-v1',
        revised_prompt, elapsed_ms. Never raises.
    """
    t0 = time.monotonic()
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter  # type: ignore
    except ImportError as exc:
        logger.warning("local_image: Pillow missing: {}", exc)
        return {
            "error": "Pillow not installed",
            "image_b64": "",
            "image_path": "",
            "size": size,
            "model": "orca-local-v1",
            "revised_prompt": prompt,
            "elapsed_ms": (time.monotonic() - t0) * 1000,
        }

    # 1. Parse size.
    try:
        w_str, h_str = size.lower().split("x")
        w, h = int(w_str), int(h_str)
    except Exception:
        w, h = 1024, 1024
    w = max(64, min(w, 2048))
    h = max(64, min(h, 2048))

    # 2. Seed colours from a stable hash of the prompt so the same
    #    prompt always produces the same image.
    digest = hashlib.sha256(prompt.encode("utf-8", errors="ignore")).digest()
    # 4 seed colours, 0-255
    seed_colours = [
        (digest[0], digest[1], digest[2]),
        (digest[3], digest[4], digest[5]),
        (digest[6], digest[7], digest[8]),
        (digest[9], digest[10], digest[11]),
    ]

    # 3. Render a multi-stop gradient.
    img = Image.new("RGB", (w, h), seed_colours[0])
    draw = ImageDraw.Draw(img)

    # Diagonal gradient
    for y in range(h):
        ratio_y = y / max(1, h - 1)
        for x in range(w):
            ratio_x = x / max(1, w - 1)
            t = (ratio_x + ratio_y) / 2
            # 2-stop gradient between colour[0] and colour[2]
            r = int(seed_colours[0][0] * (1 - t) + seed_colours[2][0] * t)
            g = int(seed_colours[0][1] * (1 - t) + seed_colours[2][1] * t)
            b = int(seed_colours[0][2] * (1 - t) + seed_colours[2][2] * t)
            draw.point((x, y), fill=(r, g, b))

    # Add a second overlay: large translucent circles in the
    # other two colours. This gives the image depth and a
    # "design" feel even with zero ML.
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    cx1, cy1 = int(w * 0.25), int(h * 0.35)
    r1 = int(min(w, h) * 0.35)
    cx2, cy2 = int(w * 0.75), int(h * 0.70)
    r2 = int(min(w, h) * 0.40)
    od.ellipse([cx1 - r1, cy1 - r1, cx1 + r1, cy1 + r1],
               fill=(*seed_colours[1], 110))
    od.ellipse([cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2],
               fill=(*seed_colours[3], 95))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    img = img.filter(ImageFilter.GaussianBlur(radius=2))

    # 4. Render the prompt text.
    draw = ImageDraw.Draw(img)
    safe_prompt = (prompt or "(no prompt)").strip()[:280]
    # Try to use a real font; fall back to the default bitmap font.
    try:
        font_big = _fit_font(draw, safe_prompt.split("\n")[0], w, h, big=True)
    except Exception:
        font_big = ImageFont.load_default()
    try:
        font_small = _fit_font(draw, safe_prompt, w, h, big=False)
    except Exception:
        font_small = ImageFont.load_default()

    # Top-left tag
    draw.rectangle([0, 0, w, int(h * 0.10)], fill=(0, 0, 0, 160))
    draw.text((20, int(h * 0.025)), "orca · local procedural art",
              fill=(255, 255, 255), font=font_small)

    # Bottom prompt text
    draw.rectangle(
        [0, int(h * 0.78), w, h], fill=(0, 0, 0, 180))
    # Word-wrap
    lines = _wrap_text(draw, safe_prompt, font_small, w - 40)
    y = int(h * 0.81)
    for line in lines[:3]:  # at most 3 lines
        draw.text((20, y), line, fill=(255, 255, 255), font=font_small)
        y += int(h * 0.045)

    # 5. Save to a temp file in the requested format.
    suffix = ".png" if output_format.upper() == "PNG" else ".jpg"
    try:
        tmp = Path(tempfile.gettempdir()) / f"orca_local_{digest[:8].hex()}{suffix}"
        if output_format.upper() == "PNG":
            img.save(tmp, format="PNG", optimize=True)
        else:
            img.convert("RGB").save(tmp, format="JPEG", quality=85)
    except Exception as exc:
        logger.warning("local_image: save failed: {}", exc)
        return {
            "error": f"save failed: {exc}",
            "image_b64": "",
            "image_path": "",
            "size": f"{w}x{h}",
            "model": "orca-local-v1",
            "revised_prompt": prompt,
            "elapsed_ms": (time.monotonic() - t0) * 1000,
        }

    # 6. Read the bytes and base64-encode (for API parity with
    #    DALL-E's b64_json response format).
    raw = tmp.read_bytes()
    import base64
    b64 = base64.b64encode(raw).decode("ascii")
    elapsed = (time.monotonic() - t0) * 1000
    logger.info(
        "local_image: prompt={!r} size={} bytes={} elapsed_ms={:.0f}",
        safe_prompt[:40], f"{w}x{h}", len(raw), elapsed,
    )
    return {
        "image_path": str(tmp),
        "image_b64": b64,
        "size": f"{w}x{h}",
        "model": "orca-local-v1",
        "revised_prompt": safe_prompt,
        "elapsed_ms": elapsed,
    }


def _fit_font(draw, text, w, h, *, big: bool = False):
    """Return an ImageFont that fits the given text width."""
    from PIL import ImageFont, ImageDraw  # type: ignore
    target_h = int(h * (0.06 if big else 0.035))
    # Try common Windows/Linux font paths.
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, target_h)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(draw, text, font, max_width) -> List[str]:
    """Naive word-wrap for PIL ImageDraw.text."""
    from PIL import ImageFont  # type: ignore
    words = text.split()
    lines: List[str] = []
    current = ""
    for w in words:
        trial = (current + " " + w).strip()
        try:
            width = draw.textlength(trial, font=font)
        except Exception:
            width = len(trial) * 10
        if width > max_width and current:
            lines.append(current)
            current = w
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


# Import tempfile here so the symbol is available to local_image
# even when the function short-circuits before using it.
import tempfile  # noqa: E402


# =====================================================================
# Local audio metadata extraction
# =====================================================================
def local_audio_info(source) -> Dict[str, Any]:
    """Return best-effort metadata for an audio source.

    Strategy:
      1. If source is a local file with a parseable header (WAV,
         AIFF, MP3 frame sync), read it directly via stdlib.
      2. Otherwise, try `ffprobe` (FFmpeg) if present on PATH.
      3. Otherwise, return a clear "metadata only" placeholder
         with whatever we could learn (file size, extension).

    Returns a dict with keys: duration_seconds, channels, sample_rate,
    bitrate, format, source, ok, note. Never raises.
    """
    info: Dict[str, Any] = {
        "duration_seconds": None,
        "channels": None,
        "sample_rate": None,
        "bitrate": None,
        "format": None,
        "source": None,
        "ok": False,
        "note": "",
    }
    if isinstance(source, (bytes, bytearray, memoryview)):
        info["format"] = "bytes"
        info["source"] = "bytes"
        info["note"] = "audio info not available for raw bytes"
        return info
    s = str(source)
    info["source"] = s[:200]
    if s.startswith(("http://", "https://")):
        info["format"] = "url"
        return {**info, "note": "URL detected; no download performed"}
    path = Path(s)
    if not path.exists():
        # Still report the extension so callers can see what was attempted
        ext = path.suffix.lstrip(".").lower() or None
        if ext:
            info["format"] = ext
        try:
            info["bitrate"] = path.stat().st_size * 8
        except Exception:
            pass
        return {**info, "note": f"file not found: {path}"}
    info["format"] = path.suffix.lstrip(".").lower() or None
    try:
        info["bitrate"] = path.stat().st_size * 8
    except Exception:
        pass

    # 1. WAV: stdlib `wave` reads RIFF headers.
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate()
                info["channels"] = w.getnchannels()
                info["sample_rate"] = rate
                info["duration_seconds"] = (
                    frames / float(rate) if rate else None
                )
                info["bitrate"] = rate * w.getsampwidth() * 8 * w.getnchannels()
                info["ok"] = True
                return info
        except Exception as exc:
            info["note"] = f"wave failed: {exc}"

    # 2. ffprobe (FFmpeg) — best-effort, no raise.
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_streams", "-of", "json",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            data = json.loads(out.stdout)
            streams = data.get("streams") or []
            if streams:
                s0 = streams[0]
                info["channels"] = s0.get("channels")
                info["sample_rate"] = s0.get("sample_rate")
                if s0.get("duration"):
                    info["duration_seconds"] = float(s0["duration"])
                if s0.get("bit_rate"):
                    info["bitrate"] = int(s0["bit_rate"])
                info["format"] = s0.get("codec_name") or info["format"]
                info["ok"] = True
                return info
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        pass

    return info


# =====================================================================
# Local DuckDuckGo search (also used by web_search_skill)
# =====================================================================
def local_search(
    query: str,
    *,
    limit: int = 5,
    timeout: float = 15.0,
) -> List[Dict[str, str]]:
    """Scrape DuckDuckGo's HTML for a result list. Pure stdlib.

    Returns a list of dicts: {title, url, snippet}. Never raises.
    """
    try:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(
            {"q": query, "kl": "us-en"}
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA,
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.debug("local_search failed: {}", exc)
        return []

    # DDG HTML uses CSS classes that change; a result block is
    # roughly: <a class="result__a" href="...">title</a> + a snippet
    # in a sibling div. We use a stable snippet-based pattern.
    results: List[Dict[str, str]] = []
    # Extract anchors with class hint or fallback to title-h2
    pattern = re.compile(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    for m in pattern.finditer(body):
        url_href = m.group(1)
        title_raw = m.group(2)
        title = re.sub(r"<[^>]+>", "", title_raw).strip()
        title = title.replace("&amp;", "&").replace("&lt;", "<").replace(
            "&gt;", ">").replace("&quot;", "\"").replace("&#x27;", "'")
        if not title:
            continue
        # Try to find the next snippet block.
        idx = m.end()
        snip_block = body[idx: idx + 2000]
        snip_m = re.search(
            r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</[at]',
            snip_block, re.DOTALL,
        )
        snippet = ""
        if snip_m:
            snippet = re.sub(r"<[^>]+>", "", snip_m.group(1)).strip()
            snippet = snippet.replace("&amp;", "&").replace("&quot;", "\"")
        results.append({
            "title": title[:200],
            "url": url_href[:500],
            "snippet": snippet[:400],
        })
        if len(results) >= limit:
            break
    return results


# =====================================================================
# Local rule-based text "completion"
# =====================================================================
def local_text_complete(prompt: str, max_tokens: int = 200) -> str:
    """A rule-based text completion that does NOT call any LLM.

    Used as a last-resort fallback for the LLM router. It implements
    a tiny subset of "completion" capabilities deterministically:

      - keyword extraction
      - sentence extraction from a passage
      - structured summarisation of bullet lists
      - polite refusals when the prompt is unanswerable

    The output is always a string and never raises.
    """
    # Defensive coercion: callers may pass ints / lists / dicts / None
    # in test or edge paths. We never raise — we treat anything that
    # doesn't look like a string as empty.
    if prompt is None:
        return ""
    if not isinstance(prompt, str):
        try:
            prompt = str(prompt)
        except Exception:
            return ""
    p = prompt.strip()
    if not p:
        return ""

    low = p.lower()
    # Detect a "summarise" instruction
    if any(w in low for w in ("summarize", "summarise", "summary", "ملخص")):
        # Take the first 3 sentences from the source.
        body = p.split(":", 1)[-1] if ":" in p else p
        sents = re.split(r"(?<=[.!?])\s+", body.strip())
        sents = [s.strip() for s in sents if s.strip()]
        top = sents[:3] if sents else [body[:200]]
        return "Summary:\n" + "\n".join(f"- {s}" for s in top)
    # Detect a "list" instruction
    if any(w in low for w in ("list", "enumerate", "اكتب", "اعمل ليست")):
        body = p.split(":", 1)[-1] if ":" in p else p
        items = re.split(r"[\n,;]", body)
        items = [i.strip(" -•\t") for i in items if i.strip()]
        if items:
            return "\n".join(f"{i+1}. {it}" for i, it in enumerate(items[:10]))
    # Detect a question mark
    if "?" in p or "؟" in p:
        return (
            "I don't have an LLM key configured, so I can't generate a "
            "free-form answer. Try `/setup <provider> <key>` to enable "
            "the LLM brain. (offline heuristic answer to: " + p[:100] + ")"
        )
    # Default: echo with a polite note.
    return (
        "(offline mode — no LLM key)\n"
        "Your message: " + p[: max(0, max_tokens * 4)]
    )


# =====================================================================
# Local transcribe placeholder
# =====================================================================
def local_transcribe_placeholder(
    source,
    duration_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Return a structured 'transcription unavailable' response.

    Better than crashing. The caller (transcribe_skill) decides whether
    to surface this to the user. The dict is shaped exactly like the
    OpenAI Whisper response so the rest of the skill is API-agnostic.
    """
    info = local_audio_info(source)
    duration = duration_seconds or info.get("duration_seconds")
    size_kb = None
    if isinstance(source, (bytes, bytearray, memoryview)):
        size_kb = round(len(bytes(source)) / 1024, 1)
    elif isinstance(source, (str, Path)):
        try:
            size_kb = round(Path(str(source)).stat().st_size / 1024, 1)
        except Exception:
            pass

    return {
        "text": "",
        "language": None,
        "duration": duration,
        "model": "orca-local-noop",
        "elapsed": 0.0,
        "segments": [],
        "ok": False,
        "fallback": True,
        "fallback_reason": "No OPENAI_API_KEY and no local Whisper model",
        "audio_info": info,
        "size_kb": size_kb,
        "note": (
            "Transcription unavailable: no LLM key and no local model. "
            "The audio file was received and analysed for metadata only."
        ),
    }


__all__ = [
    "local_image", "local_audio_info", "local_search",
    "local_text_complete", "local_transcribe_placeholder",
]
