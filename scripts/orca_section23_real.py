"""Section 23 real-data verification; read-only public Binance endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from trading_bot.analytics.capacity23 import CapacityAnalyzer
from trading_bot.analytics.compliance23 import LegalComplianceGate, check_mica_counterparty
from trading_bot.analytics.execution_quality23 import SmartOrderRouter, VenueQuote, protect_market_making, vpin
from trading_bot.analytics.infrastructure23 import InfrastructureGuard, NodeAssignment
from trading_bot.analytics.rollout23 import CapitalRamp, CodeReleaseGovernance
from trading_bot.analytics.section23 import Section23Layer
from trading_bot.data.providers import BinancePublicProvider
from trading_bot.storage.audit import AuditLog


REPORT_PATH = Path("docs/section23_report_2026-08-26.json")
AUDIT_PATH = Path("/tmp/orca_section23_audit.jsonl")


def main() -> dict:
    provider = BinancePublicProvider(timeout=20.0)
    quote = provider.fetch_quote("BTC/USDT")
    orderbook = provider.fetch_order_book("BTC/USDT", limit=20)
    rows = provider.fetch_ohlcv("BTC/USDT", interval="1m", limit=500)
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index("timestamp").sort_index()
    prices = frame["close"].tolist()
    volumes = frame["volume"].tolist()
    toxicity = vpin(prices, volumes)
    quote_protection = protect_market_making(toxicity)
    top_bid = float(orderbook["bids"][0][0]) if orderbook["bids"] else 0.0
    top_ask = float(orderbook["asks"][0][0]) if orderbook["asks"] else 0.0
    depth_notional = sum(float(price) * float(amount) for side in (orderbook["bids"], orderbook["asks"]) for price, amount in side)
    router = SmartOrderRouter()
    venue = router.choose([VenueQuote("binance_public", depth_notional, 0.0, 1.0, float(orderbook["latency_ms"]))], required_notional=1.0)
    capacity = CapacityAnalyzer().assess(strategy="diagnostic", symbol="BTC/USDT", adv_notional=max(1.0, float(frame["close"].mul(frame["volume"]).mean())), requested_notional=1.0, volatility=float(frame["close"].pct_change().std() or 0.01))
    audit = AuditLog(AUDIT_PATH)
    layer = Section23Layer(audit=audit)
    layer.configure_nodes([NodeAssignment("live-node-placeholder", "live_trading_node", ("live_execution", "kill_switch", "market_monitoring")), NodeAssignment("research-node-placeholder", "research_compute_node", ("section23_diagnostics",))])
    latency = layer.record_latency("live-node-placeholder", quote.latency_ms)
    legal = LegalComplianceGate(jurisdiction="Egypt", activity="crypto trading").assess(official_source_verified=False, qualified_counsel_approved=False)
    mica = check_mica_counterparty(counterparty="not_configured", register_checked=False, authorised=False, register_version="")
    execution = layer.execution_decision(prior_gates_allowed=True, toxicity=toxicity, venues=[VenueQuote("binance_public", depth_notional, 0.0, 1.0, float(orderbook["latency_ms"]))], required_notional=1.0, capacity=capacity)
    payload = {
        "data_source": "Binance public REST",
        "symbol": "BTC/USDT",
        "quote": {"bid": quote.bid, "ask": quote.ask, "latency_ms": quote.latency_ms, "timestamp": quote.timestamp.isoformat()},
        "orderbook": {"top_bid": top_bid, "top_ask": top_ask, "depth_notional": depth_notional, "latency_ms": orderbook["latency_ms"]},
        "ohlcv": {"bars": len(frame), "interval": "1m", "first_timestamp": frame.index[0].isoformat(), "last_timestamp": frame.index[-1].isoformat()},
        "infrastructure": {"node_separation_validated": True, "latency": latency.__dict__, "budget_basis": "configured engineering budget; not a claim of deployed hardware"},
        "execution_quality": {"vpin": toxicity.__dict__, "quote_protection": quote_protection.__dict__, "router_selected": venue.venue if venue else None, "fee_basis": "not_available_from this public endpoint; 0.0 in router is diagnostic placeholder only", "order_slices_submitted": 0},
        "capacity": capacity.__dict__,
        "defi": {"private_rpc_required": True, "transaction_submitted": False, "mev_cost_measurement": "not_available; no on-chain transaction"},
        "derivatives": {"greeks": "not_available; no options chain endpoint in the verified public provider", "vega_limit": "not_evaluated"},
        "data_quality": {"independent_second_source": "not_configured", "cross_source_signal_allowed": False, "point_in_time_archive": "not_written by this read-only verification"},
        "legal": {"local_status": legal.__dict__, "mica_status": mica.__dict__, "official_cbe_page_access": "rejected_by_source_during_research; qualified counsel required", "automated_clearance": False},
        "rollout": {"shadow_to_pilot": layer.ramp_decision(shadow_pass=False).__dict__, "code_release": layer.review_code_release(stable_version="current-stable-placeholder", staging_pass=False, independent_review=False, canary_pass=False).__dict__},
        "execution_decision": execution.__dict__,
        "audit": {"path": str(AUDIT_PATH), "events": len(AUDIT_PATH.read_text(encoding="utf-8").splitlines()) if AUDIT_PATH.exists() else 0},
        "benchmark": "not_performed; no strategy returns were generated by this read-only diagnostic",
        "execution": {"orders_submitted": 0, "live_authority": False, "keys_used": False},
        "disclosure": "This is an operational diagnostic using public market data. Fee, independent-source, options, tax, insurance, legal-clearance, and live-capital evidence were not fabricated. No performance or legal conclusion is claimed.",
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return payload


if __name__ == "__main__":
    main()
