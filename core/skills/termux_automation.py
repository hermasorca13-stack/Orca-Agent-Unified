# Backward-compat re-export. Canonical: core/termux_automation.py
# Old simulated class is removed — replaced by the real ADB-backed implementation.
from core.termux_automation import *  # noqa: F401, F403
from core.termux_automation import TermuxAutomationSkills  # noqa: F401
