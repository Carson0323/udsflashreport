from __future__ import annotations

import ast
from pathlib import Path


def test_gui_core_import_boundary_is_public_only() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "flashreport_gui"
    allowed = {"flashreport_core.api", "flashreport_core.models"}
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                if name == "flashreport_core" or name.startswith("flashreport_core."):
                    assert name in allowed, f"private core import in {path}: {name}"
