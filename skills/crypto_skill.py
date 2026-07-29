# skills/crypto_skill.py — Crypto Skill (pycoingecko-backed)
"""
Full crypto market data via CoinGecko using pycoingecko (active-maintained wrapper).
No API key required (free tier).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pycoingecko import CoinGeckoAPI
from loguru import logger

_NAME = "crypto"
_DESCRIPTION = "Full crypto market data: prices, market cap, global stats, exchanges, trending, NFTs, categories, historical charts, derivatives."
_VERSION = "2.0.0"

_cg: Optional[CoinGeckoAPI] = None


def _api() -> CoinGeckoAPI:
    global _cg
    if _cg is None:
        _cg = CoinGeckoAPI()
    return _cg


# ---------- coin price ----------
def get_price(coins: List[str], vs_currency: str = "usd") -> Dict[str, Any]:
    return _api().get_price(ids=coins, vs_currencies=vs_currency)


def get_price_full(coins: List[str], vs_currency: str = "usd") -> Dict[str, Any]:
    return _api().get_price(
        ids=coins,
        vs_currencies=vs_currency,
        include_market_cap=True,
        include_24hr_vol=True,
        include_24hr_change=True,
        include_last_updated_at=True,
    )


# ---------- coin info ----------
def get_coin(coin_id: str) -> Dict[str, Any]:
    d = _api().get_coin_by_id(coin_id)
    md = d.get("market_data", {})
    return {
        "id": d.get("id"),
        "symbol": d.get("symbol"),
        "name": d.get("name"),
        "description": (d.get("description", {}).get("en", "") or "")[:500],
        "homepage": d.get("links", {}).get("homepage", [None])[0],
        "categories": d.get("categories", []),
        "current_price_usd": md.get("current_price", {}).get("usd"),
        "market_cap_usd": md.get("market_cap", {}).get("usd"),
        "total_volume_usd": md.get("total_volume", {}).get("usd"),
        "circulating_supply": md.get("circulating_supply"),
        "total_supply": md.get("total_supply"),
        "max_supply": md.get("max_supply"),
        "ath_usd": md.get("ath", {}).get("usd"),
        "atl_usd": md.get("atl", {}).get("usd"),
        "price_change_24h": md.get("price_change_percentage_24h"),
        "price_change_7d": md.get("price_change_percentage_7d"),
        "price_change_30d": md.get("price_change_percentage_30d"),
    }


# ---------- markets ----------
def get_markets(vs_currency: str = "usd", limit: int = 50, page: int = 1) -> List[Dict[str, Any]]:
    rows = _api().get_coins_markets(vs_currency=vs_currency, per_page=limit, page=page)
    return [{
        "id": c["id"],
        "symbol": c["symbol"],
        "name": c["name"],
        "price": c["current_price"],
        "market_cap": c["market_cap"],
        "market_cap_rank": c["market_cap_rank"],
        "total_volume": c["total_volume"],
        "price_change_24h": c.get("price_change_percentage_24h"),
        "circulating_supply": c.get("circulating_supply"),
        "ath": c.get("ath"),
        "atl": c.get("atl"),
    } for c in rows]


# ---------- global ----------
def get_global() -> Dict[str, Any]:
    d = _api().get_global()
    return d.get("data", d)


# ---------- trending ----------
def get_trending() -> List[Dict[str, Any]]:
    d = _api().get_search_trending()
    out = []
    for c in d.get("coins", []):
        item = c.get("item", {})
        out.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "symbol": item.get("symbol"),
            "market_cap_rank": item.get("market_cap_rank"),
            "price_btc": item.get("price_btc"),
            "score": c.get("score"),
        })
    return out


# ---------- historical ----------
def get_history(coin_id: str, days: str = "30", vs_currency: str = "usd") -> Dict[str, Any]:
    return _api().get_coin_market_chart_by_id(id=coin_id, vs_currency=vs_currency, days=days)


def get_ohlc(coin_id: str, vs_currency: str = "usd", days: int = 7) -> List[List[float]]:
    return _api().get_coin_ohlc_by_id(id=coin_id, vs_currency=vs_currency, days=days)


# ---------- categories ----------
def get_categories() -> List[Dict[str, Any]]:
    return _api().get_coins_categories()


# ---------- search ----------
def search_coin(query: str) -> List[Dict[str, Any]]:
    return _api().get_search(query)["coins"]


# ---------- exchanges ----------
def get_exchanges(limit: int = 20) -> List[Dict[str, Any]]:
    return _api().get_exchanges(per_page=limit, page=1)


# ---------- derivatives ----------
def get_derivatives() -> List[Dict[str, Any]]:
    return _api().get_derivatives()


# ---------- meta ----------
def meta() -> Dict[str, Any]:
    return {
        "name": _NAME,
        "description": _DESCRIPTION,
        "version": _VERSION,
        "library": "pycoingecko (CoinGecko free API)",
        "auth_required": False,
    }
