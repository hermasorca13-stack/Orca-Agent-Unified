# skills/orca_skills.py - Loaded skills registry (no duplicates, single source)
from pathlib import Path
import importlib.util
from loguru import logger
from core.config import config

_LOADED = {}

def load_all():
    """Load every .py skill once. No duplicates. Single source of truth."""
    skills_dir = config.SKILLS_PATH
    if not skills_dir.exists():
        return _LOADED
    seen = set()
    for f in sorted(skills_dir.glob("*.py")):
        if f.name == "__init__.py" or f.name in seen:
            continue
        if f.stem in _LOADED:
            continue
        seen.add(f.name)
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
