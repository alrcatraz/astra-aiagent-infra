"""Unit tests for context-anchor v2.2 drop-in injection.

Run from repo root:
    python3 -m pytest work-principles/plugin/context-anchor/tests/ -v
or standalone:
    python3 work-principles/plugin/context-anchor/tests/test_inject_dir.py
"""
import os
import pathlib
import sys
import tempfile

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR.parent))  # repo parent so 'work_principles...' not needed

# Import as a package: hooks.py uses relative imports (from .state import ...)
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "context_anchor_pkg", PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
)
assert _spec is not None and _spec.loader is not None, "cannot load context-anchor package"
_pkg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pkg)
sys.modules["context_anchor_pkg"] = _pkg

# Now hooks can resolve .state relative to the package
hooks_spec = importlib.util.spec_from_file_location(
    "context_anchor_pkg.hooks", PLUGIN_DIR / "hooks.py"
)
assert hooks_spec is not None and hooks_spec.loader is not None, "cannot load context-anchor hooks"
hooks_mod = importlib.util.module_from_spec(hooks_spec)
hooks_spec.loader.exec_module(hooks_mod)
_read_inject_dir = hooks_mod._read_inject_dir  # noqa: E402


def test_no_dir_returns_empty(monkeypatch=None):
    with tempfile.TemporaryDirectory() as td:
        fake_home = pathlib.Path(td) / "no-inject-d"
        fake_home.mkdir()
        monkeypatch = monkeypatch or _FakeMonkey()
        monkeypatch.setenv("CONTEXT_ANCHOR_INJECT_DIR", str(fake_home / "inject.d"))
        assert _read_inject_dir() == ""


def test_sorted_merge(monkeypatch=None):
    with tempfile.TemporaryDirectory() as td:
        inject = pathlib.Path(td) / "inject.d"
        inject.mkdir()
        (inject / "10-first.md").write_text("FIRST", encoding="utf-8")
        (inject / "20-second.md").write_text("SECOND", encoding="utf-8")
        monkeypatch = monkeypatch or _FakeMonkey()
        monkeypatch.setenv("CONTEXT_ANCHOR_INJECT_DIR", str(inject))
        out = _read_inject_dir()
        assert "FIRST" in out and "SECOND" in out
        assert out.index("FIRST") < out.index("SECOND"), "filename order must win"
        assert out.startswith("\n\n")


def test_bad_file_skipped(monkeypatch=None):
    with tempfile.TemporaryDirectory() as td:
        inject = pathlib.Path(td) / "inject.d"
        inject.mkdir()
        (inject / "10-good.md").write_text("GOOD", encoding="utf-8")
        bad = inject / "20-bad.md"
        bad.write_bytes(b"\xff\xfe\x00invalid utf8")
        monkeypatch = monkeypatch or _FakeMonkey()
        monkeypatch.setenv("CONTEXT_ANCHOR_INJECT_DIR", str(inject))
        out = _read_inject_dir()
        assert "GOOD" in out and "invalid" not in out


def test_empty_file_skipped(monkeypatch=None):
    with tempfile.TemporaryDirectory() as td:
        inject = pathlib.Path(td) / "inject.d"
        inject.mkdir()
        (inject / "10-empty.md").write_text("", encoding="utf-8")
        (inject / "20-filled.md").write_text("FILLED", encoding="utf-8")
        monkeypatch = monkeypatch or _FakeMonkey()
        monkeypatch.setenv("CONTEXT_ANCHOR_INJECT_DIR", str(inject))
        out = _read_inject_dir()
        assert "FILLED" in out and "empty" not in out.lower()


class _FakeMonkey:
    """Minimal monkeypatch shim for standalone (non-pytest) runs."""

    def setenv(self, key, value):
        self._old = os.environ.get(key)
        os.environ[key] = value

    def __del__(self):
        if hasattr(self, "_old"):
            if self._old is None:
                os.environ.pop("CONTEXT_ANCHOR_INJECT_DIR", None)
            else:
                os.environ["CONTEXT_ANCHOR_INJECT_DIR"] = self._old


if __name__ == "__main__":
    tests = [test_no_dir_returns_empty, test_sorted_merge, test_bad_file_skipped, test_empty_file_skipped]
    passed = 0
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
