"""
ORCA Agent - Memory singleton getter
"""

from .memory import MemorySystem
from .config import get_config

_memory_instance: MemorySystem = None


def get_memory() -> MemorySystem:
    global _memory_instance
    if _memory_instance is None:
        config = get_config()
        _memory_instance = MemorySystem(
            db_path=config.memory.db_path,
            max_context_length=config.memory.max_context_length
        )
    return _memory_instance
