#!/usr/bin/env bash
# scripts/bot_doctor.sh — End-to-end production check
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "🐋 ORCA BOT DOCTOR"
echo "=================================================="

echo ""
echo "[1/5] Python version"
python3 --version

echo ""
echo "[2/5] pip deps installed"
python3 -c "import telegram, loguru, dotenv, github; print('  ✅ all core deps importable')"

echo ""
echo "[3/5] Smoke test (live API)"
python3 scripts/smoke_test.py

echo ""
echo "[4/5] Engineering doctor"
python3 orca.py doctor

echo ""
echo "[5/5] Config validation"
python3 orca.py status

echo ""
echo "=================================================="
echo "✅ ORCA BOT DOCTOR OK"
echo "=================================================="
