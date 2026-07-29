"""
ORCA Agent - Memory System
==========================
Persistent memory with SQLite backend, semantic search, and context management.
"""

import sqlite3
import json
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from contextlib import contextmanager


@dataclass
class MemoryEntry:
    """A single memory entry"""
    id: Optional[int] = None
    user_id: int = 0
    session_id: str = ""
    role: str = ""  # user, assistant, system, tool
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: float = field(default_factory=time.time)
    importance: float = 0.5  # 0.0 to 1.0
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "importance": self.importance,
            "access_count": self.access_count
        }


class MemorySystem:
    """
    Persistent memory system with:
    - SQLite storage
    - Full-text search
    - Semantic search (embeddings)
    - Importance-based retention
    - Context window management
    """
    
    def __init__(self, db_path: str = "data/memory.db", max_context_length: int = 128000):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_context_length = max_context_length
        self._init_db()
    
    @contextmanager
    def _get_conn(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_db(self):
        """Initialize database schema"""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    embedding BLOB,
                    created_at REAL NOT NULL,
                    importance REAL DEFAULT 0.5,
                    access_count INTEGER DEFAULT 0,
                    last_accessed REAL DEFAULT 0
                );
                
                CREATE INDEX IF NOT EXISTS idx_user_session 
                    ON memories(user_id, session_id);
                CREATE INDEX IF NOT EXISTS idx_created 
                    ON memories(created_at);
                CREATE INDEX IF NOT EXISTS idx_importance 
                    ON memories(importance DESC);
                
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts 
                    USING fts5(content, content_rowid='id');
                
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    last_active REAL NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    metadata TEXT DEFAULT '{}'
                );
                
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    preferences TEXT DEFAULT '{}',
                    facts TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories
                BEGIN
                    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
                END;
                
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories
                BEGIN
                    DELETE FROM memories_fts WHERE rowid = old.id;
                END;

                -- 2026-07-29 additive: keep FTS in sync on UPDATE too.
                -- Original schema only had INSERT/DELETE triggers; an
                -- in-place edit to `content` would leave the FTS index
                -- stale and break semantic search. This trigger is
                -- idempotent (CREATE TRIGGER IF NOT EXISTS) and never
                -- alters existing data.
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories
                BEGIN
                    UPDATE memories_fts SET content = new.content WHERE rowid = old.id;
                END;
            """)

            # 2026-07-29 additive: WAL mode for concurrent reads/writes.
            # The bot's loop and /memory exports now run in parallel
            # without blocking each other. Idempotent and safe on a
            # freshly-created DB.
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
    
    def add_memory(
        self,
        user_id: int,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
        importance: float = 0.5,
        embedding: Optional[List[float]] = None
    ) -> int:
        """Add a memory entry"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """INSERT INTO memories 
                   (user_id, session_id, role, content, metadata, embedding, 
                    created_at, importance, last_accessed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id, session_id, role, content,
                    json.dumps(metadata or {}),
                    json.dumps(embedding) if embedding else None,
                    time.time(), importance, time.time()
                )
            )
            return cursor.lastrowid
    
    def get_session_history(
        self, 
        user_id: int, 
        session_id: str, 
        limit: int = 50
    ) -> List[MemoryEntry]:
        """Get conversation history for a session"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM memories 
                   WHERE user_id = ? AND session_id = ?
                   ORDER BY created_at ASC LIMIT ?""",
                (user_id, session_id, limit)
            ).fetchall()
            
            # Update access stats
            if rows:
                ids = [r["id"] for r in rows]
                conn.execute(
                    f"""UPDATE memories SET access_count = access_count + 1, 
                        last_accessed = ? WHERE id IN ({','.join('?' * len(ids))})""",
                    [time.time()] + ids
                )
            
            return [self._row_to_entry(r) for r in rows]
    
    def search_memories(
        self,
        user_id: int,
        query: str,
        limit: int = 10
    ) -> List[MemoryEntry]:
        """Full-text search across memories"""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT m.* FROM memories m
                   JOIN memories_fts fts ON m.id = fts.rowid
                   WHERE memories_fts MATCH ? AND m.user_id = ?
                   ORDER BY m.importance DESC, m.created_at DESC
                   LIMIT ?""",
                (query, user_id, limit)
            ).fetchall()
            return [self._row_to_entry(r) for r in rows]
    
    def get_relevant_context(
        self,
        user_id: int,
        current_query: str,
        session_id: str,
        max_tokens: int = 8000
    ) -> List[Dict[str, str]]:
        """Get relevant context for current query"""
        # Always include recent session history
        recent = self.get_session_history(user_id, session_id, limit=20)
        
        # Search for relevant past memories
        relevant = []
        if current_query and len(current_query) > 3:
            relevant = self.search_memories(user_id, current_query, limit=5)
        
        # Build context prioritizing recent + relevant
        context = []
        char_budget = max_tokens * 4  # rough char to token ratio
        
        # Add recent messages first
        for entry in reversed(recent):
            if char_budget <= 0:
                break
            content = entry.content[:char_budget]
            context.insert(0, {"role": entry.role, "content": content})
            char_budget -= len(content)
        
        return context
    
    def get_user_facts(self, user_id: int) -> Dict[str, Any]:
        """Get stored facts about a user"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT facts, preferences FROM user_profiles WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            if row:
                return {
                    "facts": json.loads(row["facts"] or "{}"),
                    "preferences": json.loads(row["preferences"] or "{}")
                }
            return {"facts": {}, "preferences": {}}
    
    def update_user_facts(self, user_id: int, facts: Dict, preferences: Optional[Dict] = None):
        """Update user facts"""
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT facts, preferences FROM user_profiles WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            
            if existing:
                old_facts = json.loads(existing["facts"] or "{}")
                old_prefs = json.loads(existing["preferences"] or "{}")
                old_facts.update(facts)
                if preferences:
                    old_prefs.update(preferences)
                conn.execute(
                    """UPDATE user_profiles 
                       SET facts = ?, preferences = ?, updated_at = ?
                       WHERE user_id = ?""",
                    (json.dumps(old_facts), json.dumps(old_prefs), time.time(), user_id)
                )
            else:
                conn.execute(
                    """INSERT INTO user_profiles 
                       (user_id, facts, preferences, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, json.dumps(facts), json.dumps(preferences or {}), 
                     time.time(), time.time())
                )
    
    def create_session(self, session_id: str, user_id: int, platform: str) -> None:
        """Create or update a session"""
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions 
                   (id, user_id, platform, started_at, last_active)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, user_id, platform, time.time(), time.time())
            )
    
    def cleanup_old_memories(self, retention_days: int = 90):
        """Remove old unimportant memories"""
        cutoff = time.time() - (retention_days * 86400)
        with self._get_conn() as conn:
            conn.execute(
                """DELETE FROM memories 
                   WHERE created_at < ? AND importance < 0.3 AND access_count < 2""",
                (cutoff,)
            )
    
    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            metadata=json.loads(row["metadata"] or "{}"),
            created_at=row["created_at"],
            importance=row["importance"],
            access_count=row["access_count"],
            last_accessed=row["last_accessed"]
        )
    
    def get_stats(self) -> Dict[str, int]:
        """Get memory statistics"""
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
            users = conn.execute("SELECT COUNT(DISTINCT user_id) as c FROM memories").fetchone()["c"]
            sessions = conn.execute("SELECT COUNT(*) as c FROM sessions").fetchone()["c"]
            return {"total_memories": total, "unique_users": users, "sessions": sessions}

    # 2026-07-29 additive: richer diagnostics for /status and /health.
    # Never mutates state. Safe to call any time.
    def get_health_snapshot(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            row = conn.execute("PRAGMA journal_mode;").fetchone()
            journal = row[0] if row else "unknown"
            base = self.get_stats()
            base["journal_mode"] = journal
            base["db_size_bytes"] = self.db_path.stat().st_size if self.db_path.exists() else 0
            try:
                fts = conn.execute("SELECT COUNT(*) as c FROM memories_fts").fetchone()["c"]
                base["fts_rows"] = fts
            except Exception:
                base["fts_rows"] = -1
            return base
