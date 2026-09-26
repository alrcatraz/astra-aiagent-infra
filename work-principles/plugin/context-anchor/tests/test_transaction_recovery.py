"""Regression test: a poisoned PostgreSQL transaction must not wedge the anchor.

Bug (live incident, 2026-09-18 → 2026-09-23): PostgresBackend set
``autocommit = False`` on a long-lived connection but never rolled back after
an error. One driver-level failure (pg8000 error 08P01) left the transaction in
the aborted state, so every subsequent statement raised 25P02 ("current
transaction is aborted"). Because the backend is called from the
pre_llm_call / post_tool_call hooks, Hermes logged ~6400 exceptions and the
desktop UI churned for five days.

The fix has two halves, both asserted here:
  1. backend.py   — rollback after any failed/poisoning statement;
  2. state.py     — fail-open, so a storage error can never raise into a hook.

Runs against a stub connection: no live PostgreSQL required, so it stays a
unit test rather than an integration test with side effects.
"""

import json
import sys
import time as _time
import types
from pathlib import Path

# Make the plugin importable as a package member without installing it.
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT.parent))

from _pkg import load_context_anchor  # noqa: E402


class StatementError(Exception):
    """Stands in for a PostgreSQL 25P02-class failure."""


class StubCursor:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._conn.statements.append(sql.strip().split("\n")[0][:60])
        # PostgreSQL semantics: once a transaction is aborted, EVERY statement
        # on that connection fails until a rollback clears it. Modelling this
        # faithfully is what makes the concurrency test meaningful — a stub
        # that only fails on an explicit flag cannot reproduce the real wedge.
        if self._conn.txn_aborted:
            self._conn.errors += 1
            raise StatementError("current transaction is aborted")
        if self._conn.poison:
            self._conn.txn_aborted = True
            self._conn.errors += 1
            raise StatementError("current transaction is aborted")
        # Record the params actually bound, mirroring the real driver.
        self._conn.bound.append(params)

    def fetchone(self):
        return self._conn.next_row


class StubConnection:
    """Minimal DB-API surface used by PostgresBackend."""

    def __init__(self):
        self.autocommit = True  # backend sets this explicitly
        self.poison = False     # when True, the next execute aborts the txn
        self.txn_aborted = False  # sticky until rollback, like real PG
        self.statements = []
        self.bound = []
        self.commits = 0
        self.rollbacks = 0
        # Counts only error-driven recovery. `load()` deliberately rolls back
        # to end its implicit read transaction, so a raw rollback count cannot
        # distinguish a healthy code path from a poisoned one.
        self.errors = 0
        self.next_row = None
        self.closed = False
        # Serialises the stub's own state so the test measures the plugin's
        # locking, not the stub's thread-safety.
        self._stub_lock = __import__("threading").Lock()

    def cursor(self):
        return StubCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        # Real PostgreSQL clears BOTH the aborted-transaction state and the
        # pending fault on rollback; emulate that so the test proves recovery
        # rather than merely counting calls.
        self.poison = False
        self.txn_aborted = False

    def close(self):
        self.closed = True


def main() -> int:
    backend_mod, state_mod = load_context_anchor()

    conn = StubConnection()
    backend = backend_mod.PostgresBackend.__new__(backend_mod.PostgresBackend)
    backend._dsn = "stub"
    backend._conn = conn
    backend._lock = __import__("threading").RLock()
    backend._init_schema()

    failures = []

    # ── 1. A failing save must roll back AND must not raise into the caller ──
    conn.poison = True
    try:
        state_mod.get_backend = lambda: backend
        before = conn.rollbacks
        state = backend.load("sess-1")          # poisons → rollback + fail-open
        if state is None or "current_task" not in state:
            pass  # load returns defaults via state.py wrapper, checked below
        if conn.rollbacks == before:
            failures.append("load() did not roll back after a failed statement")
    except Exception as e:
        failures.append(f"load() raised through the backend: {e!r}")

    # After one rollback the stub is healthy again — the next call must work.
    if conn.poison:
        failures.append("connection still poisoned after rollback")

    # ── 2. Recovery: writes succeed once the transaction is cleared ─────────
    conn.poison = False
    try:
        backend.save("sess-1", {"k": "v"})
    except Exception as e:
        failures.append(f"save() failed after recovery: {e!r}")
    if conn.commits < 1:
        failures.append("save() did not commit")

    # ── 3. state.py must fail open even when the backend explodes ───────────
    class Exploding:
        def load(self, sid):
            raise StatementError("boom")

        def save(self, sid, st):
            raise StatementError("boom")

    state_mod.get_backend = lambda: Exploding()
    try:
        got = state_mod.get_state("sess-2")
        if "current_task" not in got:
            failures.append("get_state() returned no default state on failure")
        state_mod.set_last_tool("sess-2", "terminal", "ls")
    except Exception as e:
        failures.append(f"state API propagated a storage error: {e!r}")

    # ── 4. The original bug shape: repeated calls on a wedged connection ─────
    conn2 = StubConnection()
    b2 = backend_mod.PostgresBackend.__new__(backend_mod.PostgresBackend)
    b2._dsn = "stub"
    b2._conn = conn2
    b2._lock = __import__("threading").RLock()
    b2._init_schema()
    state_mod.get_backend = lambda: b2

    conn2.poison = True
    errors = 0
    for _ in range(5):
        try:
            state_mod.get_state("sess-3")
        except Exception:
            errors += 1
    if errors:
        failures.append(f"{errors}/5 hook-equivalent calls raised (the 25P02 cascade)")
    if conn2.rollbacks < 1:
        failures.append("no rollback issued across repeated failures")

    # ── 5. Serialisation: mutual exclusion on the shared connection ─────────
    # Hooks run on ~59 threads over ONE connection (hermes serve) with no
    # mutex in the pre-fix code. The lock is what prevents two threads from
    # interleaving transactions on that connection.
    #
    # HONEST SCOPE: this asserts that access IS serialised — it does NOT
    # reproduce the production 25P02 race. Timing-based attempts to reproduce
    # it failed: 8 threads x 40 ops produced exactly the injected error count
    # (no interleave at all), and the whole suite still passed with the lock
    # removed. Under CPython's GIL the statement and its rollback are too close
    # together for another thread to slip between them in-process. Reproducing
    # the real race needs a network round-trip in the loop, so the production
    # evidence for this fix is the lock's presence plus field observation —
    # not this test.
    import threading as _th

    conn4 = StubConnection()
    b4 = backend_mod.PostgresBackend.__new__(backend_mod.PostgresBackend)
    b4._dsn = "stub"
    b4._conn = conn4
    b4._lock = _th.RLock()
    b4._init_schema()
    state_mod.get_backend = lambda: b4

    overlap = []          # records concurrent entries, if any
    inside = [0]
    counter_lock = _th.Lock()

    def detector():
        """Sleep inside a call that holds b4._lock, recording overlap."""
        def slow():
            with counter_lock:
                inside[0] += 1
                if inside[0] > 1:
                    overlap.append(inside[0])
            _time.sleep(0.05)
            with counter_lock:
                inside[0] -= 1
        b4._run(slow)

    workers = [_th.Thread(target=detector) for _ in range(6)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=15)

    if overlap:
        failures.append(
            f"{len(overlap)} concurrent entr(ies) into the locked section "
            f"(max depth {max(overlap)}) — the shared connection is not serialised"
        )

    print("=" * 62)

    print("=" * 62)
    if failures:
        print("FAIL")
        for f in failures:
            print("  ✗", f)
        return 1
    print("PASS — poisoned transactions roll back; hooks stay fail-open")
    print(f"  rollbacks observed: {conn.rollbacks + conn2.rollbacks}, "
          f"commits: {conn.commits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
