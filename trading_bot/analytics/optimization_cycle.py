"""Cumulative, promotion-gated optimization history."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from trading_bot.analytics.backtest import run_backtest
from trading_bot.analytics.optimizer import CandidateResult, optimize_sma, sma_signal


class CumulativeOptimizer:
    def __init__(self, history_path: Path):
        self.history_path = history_path
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    def run_sma_cycle(self, train, test, *, fast_values=(5, 10, 15, 20, 30), slow_values=(40, 60, 80, 100, 150)) -> dict:
        candidate = optimize_sma(train, fast_values=fast_values, slow_values=slow_values)
        oos = run_backtest(test, sma_signal(candidate.parameters))
        accepted = bool(candidate.accepted and oos.net_pnl > 0 and oos.profit_factor > 1.0 and oos.win_rate > 0.50)
        previous = self._latest_approved()
        improved = previous is None or self._score(oos) > self._score(previous["out_of_sample"])
        promoted = bool(accepted and improved)
        record = {"ts": datetime.now(timezone.utc).isoformat(), "parameters": candidate.parameters, "in_sample": candidate.result.__dict__, "out_of_sample": oos.__dict__, "accepted": accepted, "improved_over_previous": improved, "promoted": promoted}
        records = self._records()
        records.append(record)
        self.history_path.write_text(json.dumps(records, indent=2, default=str) + "\n", encoding="utf-8")
        return record

    def _records(self) -> list[dict]:
        if not self.history_path.exists():
            return []
        return json.loads(self.history_path.read_text(encoding="utf-8"))

    def _latest_approved(self) -> dict | None:
        approved = [record for record in self._records() if record.get("promoted")]
        return approved[-1] if approved else None

    @staticmethod
    def _score(result: dict) -> tuple[float, float, float]:
        return (float(result.get("win_rate", 0.0)), float(result.get("profit_factor", 0.0)), float(result.get("net_pnl", 0.0)))
