"""Database backends for context-anchor state.

Per-session state storage with two implementations:
  - SQLite (default — zero config, stdlib)
  - PostgreSQL (set CONTEXT_ANCHOR_DATABASE_URL)

The PostgreSQL backend uses psycopg2 when available and transparently falls
back to pg8000 (pure-Python, no C deps) when it is not. Hermes' own venv
typically has no psycopg2, so the fallback is the normal path there — a hard
psycopg2 import would break every pre_llm_call / post_tool_call hook.

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


def _parse_dsn(dsn: str) -> dict:
    """Normalise a URL or libpq key=value DSN into pg8000 kwargs.

    pg8000 (1.31.x) only accepts keyword arguments — handing it a URL makes it
    treat the whole string as the username. Both DSN forms are therefore
    parsed here, and a Unix-socket host is rewritten to loopback TCP, which
    pg8000 can dial and the local server also listens on.
    """
    fields: dict = {}

    if "://" in dsn:
        from urllib.parse import urlparse, parse_qs

        u = urlparse(dsn)
        fields["user"] = u.username
        fields["password"] = u.password
        fields["host"] = u.hostname
        fields["port"] = u.port
        fields["database"] = (u.path or "").lstrip("/") or None
        qs = parse_qs(u.query)
        if fields.get("host") is None and qs.get("host"):
            fields["host"] = qs["host"][0]
        if qs.get("port"):
            fields["port"] = int(qs["port"][0])
        if fields.get("password") is None and qs.get("password"):
            fields["password"] = qs["password"][0]
    else:
        fields = {k: v for k, v in (kv.split("=", 1) for kv in dsn.split() if "=" in kv)}
        fields["database"] = fields.get("dbname")
        if fields.get("port"):
            fields["port"] = int(fields["port"])

    host = fields.get("host")
    if host and "run/postgresql" in host:
        # Unix socket → pg8000 cannot dial it; local PG also listens on 127.0.0.1.
        host = "127.0.0.1"
    fields["host"] = host or "127.0.0.1"
    fields.setdefault("port", 5432)
    fields["timeout"] = 10

    return {k: v for k, v in fields.items() if v is not None}


def _pg8000_connect(dsn: str):
    """Connect via pg8000 — pure-Python driver, no system C deps.

    Fallback for runtimes without psycopg2 (notably Hermes' own venv).
    """
    import pg8000

    return pg8000.connect(**_parse_dsn(dsn))


class PostgresBackend(Backend):
    """PostgreSQL-backed state store.

    Prefers psycopg2; degrades to pg8000 when psycopg2 is absent (the usual
    case inside Hermes' venv). Both expose the DB-API 2.0 surface this class
    uses: ``connect``, ``cursor()``, ``commit()``, ``close()`` and
    ``%s``-style paramstyle.
    """

    def __init__(self, dsn: str):
        self._dsn = dsn
        try:
            import psycopg2

            self._conn = psycopg2.connect(dsn)
            self._conn.autocommit = False
        except ImportError:
            self._conn = _pg8000_connect(dsn)
            # pg8000 exposes autocommit as a settable attribute too, but its
            # default is already manual-commit semantics; set explicitly so
            # both drivers behave identically.
            try:
                self._conn.autocommit = False
            except (AttributeError, TypeError):
                pass
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
        # libpq key=value DSN format (e.g. dbname=foo user=postgres).
        # PostgresBackend picks psycopg2 or pg8000 itself — no import here.
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
