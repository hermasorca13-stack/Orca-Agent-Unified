"""Safe model registry: model updates cannot mutate risk policy."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np


class ModelRegistry:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def train_and_stage(self, features: np.ndarray, labels: Iterable[int], name: str = "signal_model") -> Path:
        try:
            from sklearn.linear_model import LogisticRegression
        except ImportError as exc:
            raise RuntimeError("install scikit-learn to train the optional signal model") from exc
        x = np.asarray(features, dtype=float)
        y = np.asarray(tuple(labels), dtype=int)
        if x.ndim != 2 or len(x) != len(y) or len(y) < 30:
            raise ValueError("model training requires a 2-D feature matrix and at least 30 labels")
        model = LogisticRegression(max_iter=500, random_state=7).fit(x, y)
        payload = {"name": name, "trained_at": datetime.now(timezone.utc).isoformat(), "rows": len(y), "feature_count": x.shape[1], "classes": model.classes_.tolist(), "coef": model.coef_.tolist(), "intercept": model.intercept_.tolist()}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        staged = self.directory / f"{name}-{digest}.json"
        staged.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return staged

    def approve(self, staged: Path, *, reviewer: str) -> Path:
        if not reviewer.strip():
            raise ValueError("reviewer is required for model approval")
        payload = json.loads(staged.read_text(encoding="utf-8"))
        payload["approved_at"] = datetime.now(timezone.utc).isoformat()
        payload["approved_by"] = reviewer
        approved = staged.with_name(staged.stem + ".approved.json")
        approved.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return approved
