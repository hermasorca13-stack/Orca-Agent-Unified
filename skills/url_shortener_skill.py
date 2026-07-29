# skills/url_shortener_skill.py — URL Shortener Skill (pyshorteners-backed)
"""
URL shortening via pyshorteners (16+ providers in a unified interface).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import pyshorteners
from pyshorteners.exceptions import ShorteningErrorException, ExpandingErrorException

_NAME = "url_shortener"
_DESCRIPTION = "Shorten URLs via 16+ providers (is.gd, tinyurl, t.ly, bit.ly, cutt.ly, ow.ly, gg.gg, chnl.fr, clck.ru, dagd, osdb, qps.ru, short.cm, adf.ly, x.co)."
_VERSION = "2.0.0"


def _shortener() -> pyshorteners.Shortener:
    return pyshorteners.Shortener()


# ---------- public API ----------
def shorten(url: str, provider: str = "isgd", **kwargs) -> Dict[str, Any]:
    """Shorten a URL using the given provider (default: is.gd)."""
    s = _shortener()
    method = getattr(s, provider, None)
    if method is None:
        return {"error": f"unknown provider '{provider}'"}
    try:
        result = method.short(url, **kwargs)
        return {"provider": provider, "input": url, "short_url": result}
    except (ShorteningErrorException, Exception) as e:
        return {"error": str(e), "provider": provider, "input": url}


def expand(url: str, provider: str = "isgd", **kwargs) -> Dict[str, Any]:
    """Expand a short URL back to the original."""
    s = _shortener()
    method = getattr(s, provider, None)
    if method is None:
        return {"error": f"unknown provider '{provider}'"}
    try:
        result = method.expand(url, **kwargs)
        return {"provider": provider, "input": url, "expanded_url": result}
    except (ExpandingErrorException, Exception) as e:
        return {"error": str(e), "provider": provider, "input": url}


def list_providers() -> List[str]:
    """List all known shortener providers exposed by pyshorteners."""
    return [
        "adfly", "bitly", "chilpit", "clckru", "cuttly", "dagd", "gitio",
        "isgd", "nullpointer", "osdb", "owly", "post", "qpsru", "shortcm",
        "tinyurl", "tly", "xco",
    ]


def shorten_multi(url: str, providers: Optional[List[str]] = None) -> Dict[str, Any]:
    """Shorten the same URL across multiple providers in one call."""
    providers = providers or ["isgd", "tinyurl", "tly", "clckru", "owly"]
    out = {}
    for p in providers:
        out[p] = shorten(url, provider=p)
    return out


# ---------- meta ----------
def meta() -> Dict[str, Any]:
    return {
        "name": _NAME,
        "description": _DESCRIPTION,
        "version": _VERSION,
        "library": "pyshorteners",
        "providers": list_providers(),
        "auth_required_for": ["bitly", "cuttly", "adfly", "xco", "shortcm", "owly (with key)"],
    }
