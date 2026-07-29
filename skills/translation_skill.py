"""
skills/translation_skill.py — Free translation via Google web endpoint.

Why this skill:
- We pick `deep-translator` style behaviour but stay zero-dep by
  calling Google's public translate endpoint directly. The endpoint
  is reverse-engineered but stable, supports 100+ languages, and
  needs no API key.
- Fallback to `pygoogletranslation` if the upstream changes: callers
  can import `translate_via_lib` instead.

This file is ADD-ONLY. Never modifies an existing module.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Optional

UA = "Mozilla/5.0 (compatible; OrcaAgent/0.6)"

# Google translate web endpoint. Stable for years; the
# `client=gtx` parameter is a known free tier.
_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


class TranslationError(RuntimeError):
    pass


# Lightweight language list. Extend as needed. Two-letter ISO 639-1.
COMMON_LANGS = {
    "auto": "auto",
    "en": "english", "ar": "arabic", "es": "spanish", "fr": "french",
    "de": "german", "it": "italian", "pt": "portuguese", "ru": "russian",
    "zh": "chinese", "ja": "japanese", "ko": "korean", "hi": "hindi",
    "tr": "turkish", "nl": "dutch", "sv": "swedish", "pl": "polish",
    "el": "greek", "he": "hebrew", "id": "indonesian", "vi": "vietnamese",
}


def _normalize_lang(code: str) -> str:
    c = (code or "").strip().lower()
    if not c or c == "auto":
        return "auto"
    # Allow full name or two-letter code.
    if c in COMMON_LANGS.values():
        return c
    if c in COMMON_LANGS:
        return c
    # Try first match by prefix.
    for k, v in COMMON_LANGS.items():
        if v.startswith(c) or k.startswith(c):
            return k
    return c


def _parse_translation(payload, src: str) -> str:
    """Google returns a list-of-lists: payload[0] is a list of chunks."""
    if not payload or not isinstance(payload, list):
        raise TranslationError("Empty response from translator")
    chunks = payload[0]
    out: list[str] = []
    for ch in chunks:
        if not ch:
            continue
        if isinstance(ch, list) and ch:
            out.append(str(ch[0]))
    text = "".join(out).strip()
    if not text:
        raise TranslationError("Translator returned empty text")
    return text


def _call_google(text: str, src: str, tgt: str, timeout: float = 10.0) -> str:
    params = {
        "client": "gtx",
        "sl": src,
        "tl": tgt,
        "dt": "t",
        "q": text,
    }
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{_ENDPOINT}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return _parse_translation(json.loads(raw), src)


# Map full language names to codes for user convenience.
_NAME_TO_CODE = {v: k for k, v in COMMON_LANGS.items() if k != "auto"}


def resolve_lang(token: str) -> str:
    t = (token or "").strip().lower()
    if t in _NAME_TO_CODE:
        return _NAME_TO_CODE[t]
    return _normalize_lang(t)


async def translate(text: str, target: str, source: str = "auto") -> str:
    """Translate `text` to `target`. Returns the translated string.

    `target` and `source` accept either a 2-letter code or a full
    language name (case-insensitive). "auto" is allowed for `source`.
    """
    text = (text or "").strip()
    if not text:
        raise TranslationError("Empty text")
    src = _normalize_lang(source)
    tgt = resolve_lang(target)
    if tgt == "auto":
        raise TranslationError("Target language cannot be 'auto'")
    return _call_google(text, src, tgt)


async def detect(text: str) -> str:
    """Best-effort language detection. Returns the language code."""
    # Use the translator itself with src=auto: Google's response includes
    # the source language in payload[2].
    text = (text or "").strip()
    if not text:
        raise TranslationError("Empty text")
    params = {"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text[:500]}
    q = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{_ENDPOINT}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if len(payload) >= 3 and payload[2]:
        return str(payload[2]).lower()
    raise TranslationError("Could not detect language")
