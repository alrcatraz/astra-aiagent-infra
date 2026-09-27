"""Load the context-anchor plugin as a package for testing.

The plugin directory name contains a hyphen, so it cannot be imported with a
plain ``import``. This registers it under a valid module name and makes the
relative imports inside it (``from .backend import ...``) resolve.
"""

import importlib.util
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
PKG = "context_anchor"


def load_context_anchor():
    """Return ``(backend_module, state_module)`` for the plugin."""
    if PKG not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PKG,
            PLUGIN_DIR / "__init__.py",
            submodule_search_locations=[str(PLUGIN_DIR)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot build a package spec for {PLUGIN_DIR}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[PKG] = module
        spec.loader.exec_module(module)
    backend = importlib.import_module(f"{PKG}.backend")
    state = importlib.import_module(f"{PKG}.state")
    return backend, state
