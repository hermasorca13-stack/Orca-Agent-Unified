"""Durable SQLite storage for market observations and trading audit metadata."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from trading_bot.models import MarketQuote, jsonable


class MarketStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS market_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            exchange TEXT NOT NULL,
            symbol TEXT NOT NULL,
            bid REAL NOT NULL,
            ask REAL NOT NULL,
            bid_size REAL NOT NULL,
            ask_size REAL NOT NULL,
            funding_rate REAL NOT NULL,
            open_interest REAL NOT NULL,
            volume_24h REAL NOT NULL,
            latency_ms REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_market_quotes_lookup ON market_quotes(exchange, symbol, ts_utc);
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            event TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        """)
        self.connection.commit()

    def record_quote(self, quote: MarketQuote) -> None:
        self.connection.execute(
            "INSERT INTO market_quotes(ts_utc, exchange, symbol, bid, ask, bid_size, ask_size, funding_rate, open_interest, volume_24h, latency_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (quote.timestamp.isoformat(), quote.exchange, quote.symbol, quote.bid, quote.ask, quote.bid_size, quote.ask_size, quote.funding_rate, quote.open_interest, quote.volume_24h, quote.latency_ms),
        )
        self.connection.commit()

    def record_decision(self, event: str, payload: object) -> None:
        self.connection.execute(
            "INSERT INTO decisions(ts_utc, event, payload_json) VALUES(?,?,?)",
            (datetime.now(timezone.utc).isoformat(), event, json.dumps(jsonable(payload), ensure_ascii=False)),
        )
        self.connection.commit()

    def recent_quotes(self, exchange: str, symbol: str, limit: int = 100) -> list[sqlite3.Row]:
        rows = self.connection.execute(
            "SELECT * FROM market_quotes WHERE exchange=? AND symbol=? ORDER BY ts_utc DESC LIMIT ?",
            (exchange, symbol, limit),
        ).fetchall()
        return list(reversed(rows))

    def close(self) -> None:
        self.connection.close()
