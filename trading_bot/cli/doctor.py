"""Operational doctor for ORCA Max Mouny."""
from __future__ import annotations

import ast
from pathlib import Path

from trading_bot.config import load_settings


def run(root: Path | None = None) -> dict[str, object]:
    root = root or Path(__file__).resolve().parents[2]
    files = list((root / "trading_bot").rglob("*.py"))
    syntax_errors = []
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            syntax_errors.append(f"{path}: {exc}")
    settings = load_settings()
    return {
        "name": settings.name,
        "mode": settings.mode.value,
        "python_files": len(files),
        "syntax_errors": syntax_errors,
        "withdrawal_permissions": [c.name for c in settings.credentials if c.enable_withdraw],
        "safe_default": settings.mode.value == "paper" and not syntax_errors,
        "state_dir": str(settings.state_dir),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
