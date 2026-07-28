# skills/orca_skills.py - Skill registry (single source, no duplicates)
"""
Loads every .py file in skills/ exactly once.
- Maintains a module-level _LOADED dict
- Skips duplicates by stem
- Re-imports only if not yet loaded
"""
import importlib.util
from loguru import logger
from core.config import config

_LOADED: dict = {}

def load_all() -> dict:
    skills_dir = config.SKILLS_PATH
    if not skills_dir.exists():
        return _LOADED
    seen = set()
    for f in sorted(skills_dir.glob("*.py")):
        if f.name == "__init__.py" or f.stem in seen or f.stem in _LOADED:
            continue
        seen.add(f.stem)
        try:
            spec = importlib.util.spec_from_file_location(f"skill_{f.stem}", f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _LOADED[f.stem] = mod
            logger.info(f"Skill loaded: {f.stem}")
        except Exception as e:
            logger.error(f"Skill load error {f.stem}: {e}")
    return _LOADED

def get(name: str):
    return _LOADED.get(name)

def names() -> list:
    return list(_LOADED.keys())
