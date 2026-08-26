"""External market-context signals used by trade gates."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from trading_bot.data.providers import BinancePublicProvider
import pandas as pd


class MarketContextProvider:
    def __init__(self, provider: BinancePublicProvider | None = None, timeout: float = 10.0):
        self.provider = provider or BinancePublicProvider(timeout=timeout)
        self.timeout = timeout

    def fear_greed(self) -> float:
        response = httpx.get("https://api.alternative.me/fng/?limit=1", timeout=self.timeout)
        response.raise_for_status()
        return float(response.json()["data"][0]["value"])

    def btc_above_200w(self) -> bool:
        response = httpx.get(
            f"{self.provider.base_url}/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1w", "limit": "201"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        closes = pd.Series([float(row[4]) for row in rows])
        return bool(closes.iloc[-1] > closes.mean())

    def snapshot(self) -> dict[str, object]:
        return {
            "fear_greed": self.fear_greed(),
            "btc_above_200w": self.btc_above_200w(),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
