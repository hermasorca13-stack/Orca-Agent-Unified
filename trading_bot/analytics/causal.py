"""Causal validation for candidate pair relationships."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CausalReport:
    source: str
    target: str
    granger_source_to_target: float
    granger_target_to_source: float
    transfer_entropy_source_to_target: float
    transfer_entropy_target_to_source: float
    direction: str
    economic_mechanism: str
    accepted: bool


def _lag_frame(source: pd.Series, target: pd.Series, lags: int) -> tuple[np.ndarray, np.ndarray]:
    values = pd.DataFrame({"source": source, "target": target}).dropna()
    x = np.column_stack([values["target"].to_numpy()[lags - i - 1 : -i - 1 if i else None] for i in range(lags)])
    y = values["target"].to_numpy()[lags:]
    return x, y


def _granger_score(source: pd.Series, target: pd.Series, lags: int = 1) -> float:
    source_values, target_values = source.align(target, join="inner")
    frame = pd.DataFrame({"source": source_values, "target": target_values}).dropna()
    columns = {"y": frame["target"]}
    for lag in range(1, lags + 1):
        columns[f"target_lag_{lag}"] = frame["target"].shift(lag)
        columns[f"source_lag_{lag}"] = frame["source"].shift(lag)
    design = pd.DataFrame(columns).dropna()
    if len(design) <= lags + 10:
        return 0.0
    y = design.pop("y").to_numpy()
    own_columns = [column for column in design.columns if column.startswith("target_")]
    joint_columns = list(design.columns)
    own = design[own_columns].to_numpy()
    joint = design[joint_columns].to_numpy()
    own_matrix = np.column_stack([np.ones(len(own)), own])
    joint_matrix = np.column_stack([np.ones(len(joint)), joint])
    own_resid = y - own_matrix @ np.linalg.lstsq(own_matrix, y, rcond=None)[0]
    joint_resid = y - joint_matrix @ np.linalg.lstsq(joint_matrix, y, rcond=None)[0]
    improvement = max(0.0, 1.0 - float(np.var(joint_resid) / max(np.var(own_resid), 1e-12)))
    return improvement


def _transfer_entropy(source: pd.Series, target: pd.Series, bins: int = 8) -> float:
    source, target = source.align(target, join="inner")
    frame = pd.DataFrame({"source": source, "target": target}).pct_change().dropna()
    if len(frame) < 30:
        return 0.0
    source_q = pd.qcut(frame["source"], q=bins, labels=False, duplicates="drop")
    target_q = pd.qcut(frame["target"], q=bins, labels=False, duplicates="drop")
    triples = pd.DataFrame({"s": source_q.iloc[:-1].to_numpy(), "t": target_q.iloc[:-1].to_numpy(), "tn": target_q.iloc[1:].to_numpy()}).dropna()
    if triples.empty:
        return 0.0
    total = len(triples)
    entropy = 0.0
    for (_, t, tn), group in triples.groupby(["s", "t", "tn"]):
        p_joint = len(group) / total
        p_tn_t = len(triples[(triples["t"] == t) & (triples["tn"] == tn)]) / max(1, len(triples[triples["t"] == t]))
        p_tn = len(triples[triples["tn"] == tn]) / total
        entropy += p_joint * np.log(max(p_tn_t, 1e-12) / max(p_tn, 1e-12))
    return float(max(0.0, entropy))


def validate_causality(source: pd.Series, target: pd.Series, *, source_name: str, target_name: str, economic_mechanism: str, min_score: float = 0.01) -> CausalReport:
    g_st = _granger_score(source, target)
    g_ts = _granger_score(target, source)
    te_st = _transfer_entropy(source, target)
    te_ts = _transfer_entropy(target, source)
    if max(g_st, te_st) > max(g_ts, te_ts) and max(g_st, te_st) >= min_score:
        direction, accepted = f"{source_name}->{target_name}", True
    elif max(g_ts, te_ts) >= min_score:
        direction, accepted = f"{target_name}->{source_name}", True
    else:
        direction, accepted = "undetermined", False
    return CausalReport(source_name, target_name, g_st, g_ts, te_st, te_ts, direction, economic_mechanism, accepted)
