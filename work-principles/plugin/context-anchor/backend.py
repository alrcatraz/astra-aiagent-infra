"""Database backends for context-anchor state.

Per-session state storage with two implementations:
  - SQLite (default — zero config, stdlib)
  - PostgreSQL (via psycopg2, set CONTEXT_ANCHOR_DATABASE_URL)

Every session gets its own row. No global/shared fields.
"""

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path


# ── Defaults ───────────────────────────────────────────────────────

def _default_db_path() -> str:
    return str(
        Path(os.environ.get("HOME", "~/.hermes")).expanduser()
        / ".hermes" / "persistent" / "context-anchor.db"
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Abstract backend ───────────────────────────────────────────────


class Backend(ABC):
    """Per-session state store. Thread-safe within a single process."""

    @abstractmethod
    def load(self, session_id: str) -> dict | None:
        """Fetch state for a session, or None if it doesn't exist yet."""

    @abstractmethod
    def save(self, session_id: str, state: dict) -> None:
        """Upsert state for a session."""

    @abstractmethod
    def close(self) -> None:
        """Release connection resources."""


# ── SQLite backend ─────────────────────────────────────────────────


class SQLiteBackend(Backend):
    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _default_db_path()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def load(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT state_json FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def save(self, session_id: str, state: dict):
        state["updated_at"] = _now_iso()
        self._conn.execute(
            "INSERT OR REPLACE INTO sessions (session_id, state_json, updated_at) "
            "VALUES (?, ?, ?)",
            (session_id, json.dumps(state, ensure_ascii=False, default=str), state["updated_at"]),
        )
        self._conn.commit()

    def close(self):
        self._conn.close()


# ── PostgreSQL backend ─────────────────────────────────────────────


class PostgresBackend(Backend):
    def __init__(self, dsn: str):
        import psycopg2
        self._dsn = dsn
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = False
        self._init_schema()

    def _init_schema(self):
        with self._conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        self._conn.commit()

    def load(self, session_id: str) -> dict | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT state_json FROM sessions WHERE session_id = %s",
                (session_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        # JSONB returns as dict directly
        return dict(row[0]) if isinstance(row[0], dict) else json.loads(row[0])

    def save(self, session_id: str, state: dict):
        state["updated_at"] = _now_iso()
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (session_id, state_json, updated_at) "
                "VALUES (%s, %s::jsonb, %s) "
                "ON CONFLICT (session_id) DO UPDATE SET "
                "  state_json = EXCLUDED.state_json, "
                "  updated_at = EXCLUDED.updated_at",
                (session_id, json.dumps(state, ensure_ascii=False, default=str), state["updated_at"]),
            )
        self._conn.commit()

    def close(self):
        self._conn.close()


# ── Factory ────────────────────────────────────────────────────────

_BACKEND: Backend | None = None


def get_backend() -> Backend:
    """Return the singleton backend, initialised from env on first call.

    Resolution order:
      1. CONTEXT_ANCHOR_DATABASE_URL env var
         - postgresql://...  → PostgresBackend
         - sqlite:///path    → SQLiteBackend at path
      2. Fallback → SQLiteBackend at default path (~/.hermes/persistent/context-anchor.db)
    """
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND

    url = os.environ.get("CONTEXT_ANCHOR_DATABASE_URL", "").strip()

    if url.startswith("postgresql://") or url.startswith("postgres://"):
        _BACKEND = PostgresBackend(url)
    elif url.startswith("sqlite:///"):
        _BACKEND = SQLiteBackend(url[len("sqlite:///"):])
    elif "dbname=" in url or "host=" in url:
        # libpq key=value DSN format (e.g. dbname=foo user=postgres)
        import psycopg2
        _BACKEND = PostgresBackend(url)
    else:
        _BACKEND = SQLiteBackend()

    return _BACKEND


def close_backend():
    """Release the backend connection (called during plugin teardown if needed)."""
    global _BACKEND
    if _BACKEND is not None:
        _BACKEND.close()
        _BACKEND = None
