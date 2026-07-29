"""
skills/fx_skill.py — Currency exchange via Frankfurter (no API key).

Why this skill:
- Frankfurter is the consensus 2026 winner for free FX: unlimited
  requests, no key, ECB reference data, 33 currencies, historical
  back to 1999. Self-hostable.
- Pure stdlib `urllib` keeps the dependency surface zero.

Public surface:
- `rate(amount, base, target)` — convert.
- `series(base, target, days=30)` — recent time series.
- `list_currencies()` — supported currency codes + names.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

UA = "Orca-Agent/0.6"
_BASE = "https://api.frankfurter.dev/v1"


class FXError(RuntimeError):
    pass


def _http(path: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
    url = f"{_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def list_currencies() -> str:
    data = _http("/currencies")
    items = data.items() if isinstance(data, dict) else []
    lines = ["💱 *Supported currencies*", ""]
    for code, name in sorted(items):
        lines.append(f"• `{code}` — {name}")
    return "\n".join(lines)


async def rate(amount: float, base: str, target: str) -> str:
    base = base.upper().strip()
    target = target.upper().strip()
    if not base or not target:
        raise FXError("Both base and target currencies are required")
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        raise FXError(f"Invalid amount: {amount!r}")
    data = _http("/latest", {"base": base, "symbols": target})
    rates = data.get("rates") or {}
    if target not in rates:
        raise FXError(f"Rate for {target} not found")
    r = rates[target]
    converted = amt * r
    return (
        f"💱 *{amt:,.2f} {base}* → *{converted:,.2f} {target}*\n"
        f"Rate: 1 {base} = {r} {target}  •  Date: {data.get('date', '?')}"
    )


async def series(base: str, target: str, days: int = 30) -> str:
    base = base.upper().strip()
    target = target.upper().strip()
    days = max(1, min(365, int(days)))
    end = date.today()
    start = end - timedelta(days=days)
    data = _http(
        f"/{start.isoformat()}..{end.isoformat()}",
        {"base": base, "symbols": target},
    )
    r = data.get("rates") or {}
    if not r:
        return f"📭 No data for {base}→{target}"
    lines = [f"📈 *{base}→{target} (last {days}d)*", ""]
    # r is a dict of date → {code: rate}; show first/last/min/max.
    rates = [v.get(target) for v in r.values() if v.get(target) is not None]
    if not rates:
        return f"📭 No data for {base}→{target}"
    lo, hi = min(rates), max(rates)
    first_date, last_date = min(r.keys()), max(r.keys())
    lines += [
        f"First ({first_date}): {r[first_date].get(target)}",
        f"Last  ({last_date}): {r[last_date].get(target)}",
        f"Min: {lo}  •  Max: {hi}",
    ]
    return "\n".join(lines)
