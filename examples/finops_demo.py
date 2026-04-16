"""
examples/finops_demo.py
=======================
Standalone FinOps demo that loads CUR data and prints a savings report.
Bypasses finops_intelligence/__init__.py (which has broken imports for
AnalyticsConfig / UnitEconomicsConfig stubs) by importing CLI submodules
directly.

Usage:
    python examples/finops_demo.py analyze --cur examples/sample_cur.csv --spend 15000 --no-ai
"""
from __future__ import annotations
import sys
import importlib.util
import types
from pathlib import Path

# Add repo root so relative imports resolve
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# Create a minimal finops_intelligence package stub in sys.modules so that
# relative imports inside cli.py / cur_ingestor.py / etc. resolve correctly,
# without triggering __init__.py's broken imports.
_FI_PKG = types.ModuleType("finops_intelligence")
_FI_PKG.__path__ = [str(_REPO_ROOT / "finops_intelligence")]
_FI_PKG.__package__ = "finops_intelligence"
_FI_PKG.__spec__ = importlib.util.spec_from_file_location(
    "finops_intelligence",
    str(_REPO_ROOT / "finops_intelligence" / "__init__.py"),
)
sys.modules.setdefault("finops_intelligence", _FI_PKG)


def _load_submod(name: str) -> types.ModuleType:
    """Load a finops_intelligence submodule without triggering __init__."""
    mod_name = f"finops_intelligence.{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    path = _REPO_ROOT / "finops_intelligence" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "finops_intelligence"
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-load submodules the CLI will need (in dependency order)
for _sub in ["cur_ingestor", "ri_sp_optimizer", "right_sizer",
             "carbon_tracker", "savings_reporter", "cli"]:
    _load_submod(_sub)

# Run the CLI
_cli = sys.modules["finops_intelligence.cli"]
if __name__ == "__main__":
    _cli.main()
