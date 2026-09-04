from __future__ import annotations

"""JSON report serialization."""

import json
from pathlib import Path
from typing import Any


def write_json(report: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = ["write_json"]
