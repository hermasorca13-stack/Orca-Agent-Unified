"""Auditable technical indicators used by signal gates."""
from __future__ import annotations

import math
from typing import Iterable

import pandas as pd


def ema(values: pd.Series, period: int) -> pd.Series:
    return values.astype(float).ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = frame["high"].astype(float), frame["low"].astype(float), frame["close"].astype(float)
    prev = close.shift(1)
    true_range = pd.concat([(high - low), (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def stochastic_rsi(close: pd.Series, rsi_period: int = 14, window: int = 14, smooth: int = 3) -> pd.Series:
    values = rsi(close, rsi_period)
    low = values.rolling(window).min()
    high = values.rolling(window).max()
    raw = (values - low) / (high - low).replace(0.0, float("nan"))
    return raw.rolling(smooth).mean().clip(0.0, 1.0)


def heikin_ashi(frame: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    result["close"] = (frame["open"] + frame["high"] + frame["low"] + frame["close"]) / 4.0
    result["open"] = 0.0
    if len(result):
        result.iloc[0, result.columns.get_loc("open")] = (frame["open"].iloc[0] + frame["close"].iloc[0]) / 2.0
        for index in range(1, len(result)):
            result.iloc[index, result.columns.get_loc("open")] = (result["open"].iloc[index - 1] + result["close"].iloc[index - 1]) / 2.0
    result["high"] = pd.concat([frame["high"], result["open"], result["close"]], axis=1).max(axis=1)
    result["low"] = pd.concat([frame["low"], result["open"], result["close"]], axis=1).min(axis=1)
    return result


def elder_weight_oscillator(frame: pd.DataFrame, period: int = 13) -> pd.Series:
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    weights = frame["volume"].astype(float).replace(0.0, float("nan"))
    weighted = (typical * weights).rolling(period).sum() / weights.rolling(period).sum()
    return weighted - ema(weighted, period)


def z_score(values: pd.Series, window: int = 60) -> pd.Series:
    mean = values.rolling(window).mean()
    std = values.rolling(window).std(ddof=0).replace(0.0, float("nan"))
    return (values - mean) / std


def beta(returns_a: pd.Series, returns_b: pd.Series, window: int = 60) -> pd.Series:
    covariance = returns_a.rolling(window).cov(returns_b)
    variance = returns_b.rolling(window).var(ddof=0).replace(0.0, float("nan"))
    return covariance / variance


def enrich(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"OHLCV frame missing columns: {sorted(missing)}")
    out = frame.copy()
    out["ema_50"] = ema(out["close"], 50)
    out["ema_100"] = ema(out["close"], 100)
    out["ema_200"] = ema(out["close"], 200)
    out["rsi_14"] = rsi(out["close"], 14)
    out["stoch_rsi"] = stochastic_rsi(out["close"])
    out["atr_14"] = atr(out)
    out["atr_pct"] = out["atr_14"] / out["close"]
    out["volume_sma_20"] = out["volume"].rolling(20).mean()
    out["elder_wo"] = elder_weight_oscillator(out)
    ha = heikin_ashi(out)
    out["ha_bullish"] = ha["close"] >= ha["open"]
    out["ha_bearish"] = ha["close"] < ha["open"]
    return out
