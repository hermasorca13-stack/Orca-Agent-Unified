# skills/stocks_skill.py — Stocks Skill (yfinance-backed)
"""
Full stock market data via Yahoo Finance using yfinance (de-facto standard, 13k+ stars).
Provides historical data, dividends, splits, financials, options, news, recommendations, holders.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import yfinance as yf

_NAME = "stocks"
_DESCRIPTION = "Full stock market data: prices, history, dividends, splits, options, financials, news, recommendations, holders, analyst targets."
_VERSION = "2.0.0"


def _ticker(symbol: str) -> yf.Ticker:
    return yf.Ticker(symbol)


# ---------- quote ----------
def get_quote(symbol: str) -> Dict[str, Any]:
    t = _ticker(symbol)
    info = t.info or {}
    return {
        "symbol": symbol,
        "short_name": info.get("shortName"),
        "long_name": info.get("longName"),
        "currency": info.get("currency"),
        "exchange": info.get("exchange"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "website": info.get("website"),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "previous_close": info.get("previousClose"),
        "open": info.get("open"),
        "day_low": info.get("dayLow"),
        "day_high": info.get("dayHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "volume": info.get("volume"),
        "avg_volume": info.get("averageVolume"),
    }


def get_quotes(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for s in symbols:
        try:
            out[s] = get_quote(s)
        except Exception as e:
            out[s] = {"error": str(e)}
    return out


# ---------- history ----------
def get_history(symbol: str, period: str = "1mo", interval: str = "1d") -> List[Dict[str, Any]]:
    """period: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
       interval: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo"""
    h = _ticker(symbol).history(period=period, interval=interval)
    out = []
    for idx, row in h.iterrows():
        out.append({
            "date": idx.isoformat(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]) if row["Volume"] is not None else None,
        })
    return out


# ---------- dividends / splits ----------
def get_dividends(symbol: str) -> Dict[str, float]:
    div = _ticker(symbol).dividends
    return {idx.date().isoformat(): float(val) for idx, val in div.items()}


def get_splits(symbol: str) -> Dict[str, float]:
    sp = _ticker(symbol).splits
    return {idx.date().isoformat(): float(val) for idx, val in sp.items()}


# ---------- financials ----------
def get_income_stmt(symbol: str) -> Dict[str, Any]:
    t = _ticker(symbol)
    return {"income_stmt": t.income_stmt.to_dict() if t.income_stmt is not None else {},
            "quarterly": t.quarterly_income_stmt.to_dict() if t.quarterly_income_stmt is not None else {}}


def get_balance_sheet(symbol: str) -> Dict[str, Any]:
    t = _ticker(symbol)
    return {"balance_sheet": t.balance_sheet.to_dict() if t.balance_sheet is not None else {},
            "quarterly": t.quarterly_balance_sheet.to_dict() if t.quarterly_balance_sheet is not None else {}}


def get_cashflow(symbol: str) -> Dict[str, Any]:
    t = _ticker(symbol)
    return {"cashflow": t.cashflow.to_dict() if t.cashflow is not None else {},
            "quarterly": t.quarterly_cashflow.to_dict() if t.quarterly_cashflow is not None else {}}


# ---------- holders / insider / institutional ----------
def get_holders(symbol: str) -> Dict[str, Any]:
    t = _ticker(symbol)
    return {
        "major": t.major_holders.to_dict() if t.major_holders is not None else {},
        "institutional": t.institutional_holders.head(20).to_dict() if t.institutional_holders is not None else {},
        "mutualfund": t.mutualfund_holders.head(20).to_dict() if t.mutualfund_holders is not None else {},
        "insider_purchases": t.insider_purchases.to_dict() if t.insider_purchases is not None else {},
        "insider_transactions": t.insider_transactions.head(20).to_dict() if t.insider_transactions is not None else {},
    }


# ---------- analyst ----------
def get_recommendations(symbol: str) -> List[Dict[str, Any]]:
    recs = _ticker(symbol).recommendations
    if recs is None or recs.empty:
        return []
    return recs.tail(30).reset_index().to_dict(orient="records")


def get_analyst_targets(symbol: str) -> Dict[str, Any]:
    t = _ticker(symbol)
    return {
        "current": t.info.get("currentPrice"),
        "target_low": t.info.get("targetLowPrice"),
        "target_mean": t.info.get("targetMeanPrice"),
        "target_median": t.info.get("targetMedianPrice"),
        "target_high": t.info.get("targetHighPrice"),
        "recommendation": t.info.get("recommendationKey"),
        "num_analysts": t.info.get("numberOfAnalystOpinions"),
    }


# ---------- news ----------
def get_news(symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
    n = _ticker(symbol).news or []
    out = []
    for item in n[:limit]:
        out.append({
            "title": item.get("title"),
            "publisher": item.get("publisher"),
            "link": item.get("link"),
            "published": item.get("providerPublishTime"),
            "type": item.get("type"),
        })
    return out


# ---------- options ----------
def get_option_expirations(symbol: str) -> List[str]:
    return list(_ticker(symbol).options or [])


def get_option_chain(symbol: str, expiration: str) -> Dict[str, Any]:
    chain = _ticker(symbol).option_chain(expiration)
    return {
        "calls": chain.calls.head(50).to_dict(orient="records"),
        "puts": chain.puts.head(50).to_dict(orient="records"),
    }


# ---------- search ----------
def search_symbols(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    res = yf.Search(query, max_results=limit).all
    out = []
    for q in res.get("quotes", [])[:limit]:
        out.append({
            "symbol": q.get("symbol"),
            "short_name": q.get("shortname"),
            "exchange": q.get("exchange"),
            "type": q.get("quoteType"),
        })
    return out


# ---------- meta ----------
def meta() -> Dict[str, Any]:
    return {
        "name": _NAME,
        "description": _DESCRIPTION,
        "version": _VERSION,
        "library": "yfinance (Yahoo Finance unofficial)",
        "auth_required": False,
    }
