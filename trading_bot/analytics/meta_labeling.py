"""Primary-signal filtering with ATR-scaled triple barriers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BarrierEvent:
    index: object
    direction: float
    label: int
    return_pct: float
    barrier: str
    horizon: int


def _atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    previous = frame["close"].shift(1)
    true_range = pd.concat([(frame["high"] - frame["low"]), (frame["high"] - previous).abs(), (frame["low"] - previous).abs()], axis=1).max(axis=1)
    return true_range.rolling(window).mean()


def triple_barrier_labels(frame: pd.DataFrame, primary_signal: Callable[[pd.DataFrame], float | None], *, profit_atr: float = 1.5, stop_atr: float = 1.0, horizon: int = 24, atr_window: int = 14) -> tuple[pd.DataFrame, list[BarrierEvent]]:
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    atr = _atr(frame, atr_window)
    features: list[dict[str, float]] = []
    events: list[BarrierEvent] = []
    for i in range(max(atr_window, 20), len(frame) - horizon - 1):
        history = frame.iloc[: i + 1]
        direction = primary_signal(history)
        if direction in (None, 0):
            continue
        entry = float(frame["close"].iloc[i])
        vol = float(atr.iloc[i])
        if not np.isfinite(vol) or vol <= 0:
            continue
        target = entry + direction * profit_atr * vol
        stop = entry - direction * stop_atr * vol
        label, barrier, exit_price = 0, "timeout", float(frame["close"].iloc[min(i + horizon, len(frame) - 1)])
        for j in range(i + 1, min(i + horizon + 1, len(frame))):
            high, low = float(frame["high"].iloc[j]), float(frame["low"].iloc[j])
            profit_hit = high >= target if direction > 0 else low <= target
            stop_hit = low <= stop if direction > 0 else high >= stop
            if profit_hit and stop_hit:
                label, barrier, exit_price = 0, "ambiguous_same_bar_stop_first", stop
                break
            if profit_hit:
                label, barrier, exit_price = 1, "profit", target
                break
            if stop_hit:
                label, barrier, exit_price = 0, "stop", stop
                break
        signed_return = direction * (exit_price - entry) / entry
        row = frame.iloc[i]
        features.append({"return_1": float(frame["close"].pct_change().iloc[i]), "return_5": float(frame["close"].pct_change(5).iloc[i]), "atr_pct": vol / entry, "volume_z": float((frame["volume"].iloc[i] - frame["volume"].rolling(30).mean().iloc[i]) / max(frame["volume"].rolling(30).std().iloc[i], 1e-12)), "direction": float(direction), "index": i})
        events.append(BarrierEvent(frame.index[i], float(direction), label, float(signed_return), barrier, min(horizon, len(frame) - i - 1)))
    return pd.DataFrame(features).set_index("index"), events


class MetaLabeler:
    def __init__(self, *, min_probability: float = 0.55, random_state: int = 7):
        self.min_probability = min_probability
        self.random_state = random_state
        self.model = None
        self.feature_columns: list[str] = []

    def fit(self, features: pd.DataFrame, labels: list[int] | np.ndarray) -> "MetaLabeler":
        from sklearn.ensemble import RandomForestClassifier
        x = features.drop(columns=["index"], errors="ignore").replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
        y = np.asarray(tuple(labels), dtype=int)
        if len(x) != len(y):
            raise ValueError("features and labels must be aligned row-for-row")
        if len(x) < 30 or len(np.unique(y)) < 2:
            raise ValueError("meta-labeler requires at least 30 valid observations and two classes")
        self.feature_columns = list(x.columns)
        self.model = RandomForestClassifier(n_estimators=200, min_samples_leaf=5, class_weight="balanced", random_state=self.random_state, n_jobs=1)
        self.model.fit(x[self.feature_columns], y)
        return self

    def probability(self, features: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("meta-labeler is not fitted")
        x = features.reindex(columns=self.feature_columns).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        classes = list(self.model.classes_)
        positive = classes.index(1) if 1 in classes else 0
        return self.model.predict_proba(x)[:, positive]

    def accept(self, features: pd.DataFrame) -> np.ndarray:
        return self.probability(features) >= self.min_probability

    def size_multiplier(self, features: pd.DataFrame, *, fractional_kelly: float = 0.25) -> np.ndarray:
        probabilities = self.probability(features)
        edge = np.maximum(2.0 * probabilities - 1.0, 0.0)
        return np.clip(fractional_kelly * edge, 0.0, 1.0)
