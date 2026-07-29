"""
skills/tts_skill.py — Text-to-Speech via edge-tts (no API key, 318 voices).

Why this skill:
- edge-tts is the consensus 2026 winner for free TTS: no signup, no
  rate limits, taps Microsoft Edge's neural voices (en-US-AriaNeural,
  ar-EG-SalmaNeural, etc.). 318 voices across 100+ locales.
- We call it via subprocess so we don't need edge-tts in our
  requirements (it's pulled at runtime if missing).

Public surface:
- `synthesize(text, voice="en-US-AriaNeural", rate=0, volume=0)` — writes
  an MP3 to a temp path and returns that path.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


# A small curated voice list for quick `/voice` lookups.
VOICES = {
    "en-US-AriaNeural": "English (US) — Aria (female, warm)",
    "en-US-GuyNeural": "English (US) — Guy (male, casual)",
    "en-GB-RyanNeural": "English (UK) — Ryan (male)",
    "ar-EG-SalmaNeural": "Arabic (EG) — Salma (female)",
    "ar-SA-ZariyahNeural": "Arabic (SA) — Zariyah (female)",
    "fr-FR-DeniseNeural": "French (FR) — Denise (female)",
    "de-DE-KatjaNeural": "German (DE) — Katja (female)",
    "es-ES-ElviraNeural": "Spanish (ES) — Elvira (female)",
    "ru-RU-SvetlanaNeural": "Russian (RU) — Svetlana (female)",
    "zh-CN-XiaoxiaoNeural": "Chinese (CN) — Xiaoxiao (female)",
    "ja-JP-NanamiNeural": "Japanese (JP) — Nanami (female)",
    "hi-IN-SwaraNeural": "Hindi (IN) — Swara (female)",
    "tr-TR-EmelNeural": "Turkish (TR) — Emel (female)",
}


class TTSError(RuntimeError):
    pass


def _edge_tts_bin() -> Optional[str]:
    """Return the path to the `edge-tts` CLI or None if not installed."""
    return shutil.which("edge-tts")


def _ensure_edge_tts() -> str:
    """Make sure the edge-tts CLI exists. Tries `pip install --user`."""
    p = _edge_tts_bin()
    if p:
        return p
    # Best-effort install into the active environment.
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", "edge-tts"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        raise TTSError(
            "edge-tts not installed and auto-install failed. "
            "Run: pip install edge-tts"
        ) from exc
    p = _edge_tts_bin()
    if not p:
        raise TTSError("edge-tts still not found on PATH after install")
    return p


async def synthesize(
    text: str,
    voice: str = "en-US-AriaNeural",
    rate: int = 0,
    volume: int = 0,
    out_dir: Optional[str] = None,
) -> str:
    """Synthesize `text` to an MP3 file. Returns the file path."""
    text = (text or "").strip()
    if not text:
        raise TTSError("Empty text")
    if voice not in VOICES and not voice.endswith("Neural"):
        # Allow any *Neural voice even if not in our curated list.
        pass

    bin_path = _ensure_edge_tts()
    outdir = Path(out_dir) if out_dir else Path(tempfile.gettempdir())
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"orca_tts_{os.getpid()}_{abs(hash(text)) & 0xffff}.mp3"

    rate_arg = f"{rate:+d}%"
    vol_arg = f"{volume:+d}%"
    cmd = [
        bin_path,
        "--text", text,
        "--voice", voice,
        "--rate", rate_arg,
        "--volume", vol_arg,
        "--write-media", str(out),
    ]
    # `edge-tts` is sync; run it in a thread to keep the bot loop non-blocked.
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0 or not out.exists():
        raise TTSError(f"edge-tts failed: {err.decode('utf-8', 'replace')[:200]}")
    return str(out)


async def list_voices() -> str:
    """Return a Markdown card with the curated voice list."""
    lines = ["🎙 *Available voices*", ""]
    for v, label in VOICES.items():
        lines.append(f"• `{v}` — {label}")
    lines += ["", "_Or pass any `xx-XX-NameNeural` voice Microsoft Edge supports._"]
    return "\n".join(lines)
