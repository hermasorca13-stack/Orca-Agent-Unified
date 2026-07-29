"""
core/__main__.py — Allows `python -m core` as alias to `python orca.py status`
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if __name__ == "__main__":
    # Delegate to orca.py with default status
    import runpy
    runpy.run_path(str(Path(__file__).resolve().parent.parent / "orca.py"), run_name="__main__")
