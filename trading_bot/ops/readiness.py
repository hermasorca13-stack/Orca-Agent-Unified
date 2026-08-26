"""Operational readiness checks with an explicit safe default."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import os

from trading_bot.config.settings import ConfigurationError, load_settings


@dataclass(frozen=True)
class ReadinessReport:
    paper_ready: bool
    sandbox_credentials_present: bool
    sandbox_probe_required: bool
    live_credentials_present: bool
    live_confirmation_present: bool
    live_ready: bool
    withdrawals_enabled: bool
    syntax_ok: bool
    state_dir: str
    reasons: tuple[str, ...]


def check_readiness() -> ReadinessReport:
    reasons: list[str] = []
    syntax_ok = True
    paper_ready = False
    sandbox_present = False
    live_present = False
    withdrawals = False
    state_dir = "data/orca_max_mouny"
    try:
        settings = load_settings()
        paper_ready = True
        state_dir = str(settings.state_dir)
        sandbox_present = any(credential.configured and credential.sandbox for credential in settings.credentials)
        live_present = any(credential.configured and not credential.sandbox for credential in settings.credentials)
        withdrawals = any(credential.enable_withdraw for credential in settings.credentials)
    except (ConfigurationError, OSError, ValueError) as exc:
        reasons.append(f"configuration:{type(exc).__name__}")
    for path in Path("trading_bot").rglob("*.py"):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError:
            syntax_ok = False
            reasons.append(f"syntax:{path}")
    if withdrawals:
        reasons.append("withdrawals_must_remain_disabled")
    confirmation = os.getenv("ORCA_LIVE_CONFIRM", "") == "I_UNDERSTAND_ORCA_LIVE"
    live_ready = bool(live_present and confirmation and syntax_ok and not withdrawals)
    if not sandbox_present:
        reasons.append("sandbox_credentials_not_present_or_not_verified")
    if not live_ready:
        reasons.append("live_slot_is_optional_and_not_ready")
    return ReadinessReport(paper_ready, sandbox_present, not sandbox_present, live_present, confirmation, live_ready, withdrawals, syntax_ok, state_dir, tuple(reasons))


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="ORCA readiness check; never prints secret values")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_readiness()
    import json
    print(json.dumps(asdict(report), indent=2))
    return 0 if report.paper_ready and report.syntax_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
