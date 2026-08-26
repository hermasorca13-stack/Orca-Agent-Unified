"""Deterministic technical signal model for directional legs."""
from __future__ import annotations

import pandas as pd

from trading_bot.analytics.indicators import enrich
from trading_bot.models import Signal, Side


def technical_signal(frame: pd.DataFrame, symbol: str, strategy: str = "momentum") -> Signal | None:
    data = enrich(frame)
    row = data.iloc[-1]
    if pd.isna(row[["ema_50", "ema_100", "ema_200", "rsi_14", "stoch_rsi", "atr_pct", "volume_sma_20"]]).any():
        return None
    bullish = [
        row["close"] > row["ema_100"],
        row["ema_50"] > row["ema_200"],
        row["rsi_14"] > 50.0,
        bool(row["ha_bullish"]),
        row["stoch_rsi"] > 0.50,
        row["volume"] > row["volume_sma_20"],
    ]
    bearish = [
        row["close"] < row["ema_100"],
        row["ema_50"] < row["ema_200"],
        row["rsi_14"] < 50.0,
        bool(row["ha_bearish"]),
        row["stoch_rsi"] < 0.50,
        row["volume"] > row["volume_sma_20"],
    ]
    long_count, short_count = sum(bullish), sum(bearish)
    if max(long_count, short_count) < 3 or long_count == short_count:
        return None
    side = Side.BUY if long_count > short_count else Side.SELL
    confirmations = max(long_count, short_count)
    close = float(row["close"])
    atr_value = float(row["atr_14"])
    stop = close - 2.0 * atr_value if side == Side.BUY else close + 2.0 * atr_value
    targets = (close + 2.0 * (close - stop), close + 3.0 * (close - stop)) if side == Side.BUY else (close - 2.0 * (stop - close), close - 3.0 * (stop - close))
    return Signal(
        strategy=strategy,
        symbol=symbol,
        side=side,
        score=float(confirmations / len(bullish)),
        expected_edge_bps=float(abs(close - stop) / close * 10_000 * 2),
        stop_price=stop,
        target_prices=tuple(float(x) for x in targets),
        confidence=float(confirmations / len(bullish)),
        reasons=tuple(["EMA100", "EMA50/200", "RSI", "Heikin-Ashi", "StochRSI", "volume>SMA20"][i] for i, enabled in enumerate(bullish if side == Side.BUY else bearish) if enabled),
    )
