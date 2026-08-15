"""End-to-end smoke test: on_pre_llm_call with a drop-in directory."""
import os
import pathlib
import sys
import tempfile
import importlib.util

PLUGIN_DIR = pathlib.Path("work-principles/plugin/context-anchor").resolve()
spec = importlib.util.spec_from_file_location(
    "capkg", PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
)
assert spec is not None and spec.loader is not None
pkg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pkg)
sys.modules["capkg"] = pkg

hs = importlib.util.spec_from_file_location("capkg.hooks", PLUGIN_DIR / "hooks.py")
assert hs is not None and hs.loader is not None
hm = importlib.util.module_from_spec(hs)
hs.loader.exec_module(hm)

with tempfile.TemporaryDirectory() as td:
    inj = pathlib.Path(td) / "inject.d"
    inj.mkdir()
    (inj / "10-constellation.md").write_text(
        "[CONSTELLATION]\n  dispatch: dsh(ACP)/OpenCode(ACP); guardian: no device",
        encoding="utf-8",
    )
    os.environ["CONTEXT_ANCHOR_INJECT_DIR"] = str(inj)
    out = hm.on_pre_llm_call("BASE-SYSTEM-PROMPT")
    os.environ.pop("CONTEXT_ANCHOR_INJECT_DIR", None)

    checks = {
        "BASE prompt intact": "BASE-SYSTEM-PROMPT" in out,
        "anchor block present": "[CONTEXT ANCHOR]" in out,
        "constellation injected": "[CONSTELLATION]" in out,
        "inject after anchor": out.index("[CONSTELLATION]") > out.index("[CONTEXT ANCHOR]"),
    }
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print("--- tail ---")
    print(out[-300:])
    sys.exit(0 if all(checks.values()) else 1)
