from __future__ import annotations

"""Small, deterministic loaders for the repository's executable spec files."""

import sys
from pathlib import Path
from typing import Any


def _runtime_roots() -> tuple[Path, ...]:
    """Return source and frozen-package roots in deterministic lookup order."""

    source_root = Path(__file__).resolve().parents[2]
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            meipass_root = Path(meipass)
            roots.extend((meipass_root, meipass_root / "_internal"))
        executable_root = Path(sys.executable).resolve().parent
        roots.extend((executable_root / "_internal", executable_root))
    roots.append(source_root)

    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return tuple(unique)


def resolve_runtime_resource(relative_path: str | Path) -> Path:
    """Resolve a public repository resource in source or a frozen package."""

    relative = Path(relative_path)
    for root in _runtime_roots():
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return _runtime_roots()[-1] / relative


def _split_inline_items(value: str) -> list[str]:
    items: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(value):
        if char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(value[start:index].strip())
            start = index + 1
    items.append(value[start:].strip())
    return [item for item in items if item]


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return None
    if value.startswith("{") and value.endswith("}"):
        result: dict[str, Any] = {}
        inner = value[1:-1].strip()
        if not inner:
            return result
        for item in _split_inline_items(inner):
            if ":" not in item:
                raise ValueError(f"invalid inline findings YAML value: {value}")
            key, nested = item.split(":", 1)
            result[key.strip().strip("\"'")] = _parse_scalar(nested.strip())
        return result
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [_parse_scalar(item) for item in _split_inline_items(inner)]
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _fallback_yaml_load(path: Path) -> dict[str, Any]:
    """Parse the deliberately constrained findings registry without PyYAML."""

    result: dict[str, Any] = {"findings": []}
    current: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped == "findings:":
            continue
        if stripped.startswith("- id:"):
            current = {"id": _parse_scalar(stripped.split(":", 1)[1])}
            result["findings"].append(current)
            continue
        if ":" not in stripped:
            raise ValueError(f"unsupported findings YAML line: {raw_line}")
        key, value = stripped.split(":", 1)
        parsed = _parse_scalar(value)
        if current is not None and line.startswith("    "):
            current[key.strip()] = parsed
        else:
            result[key.strip()] = parsed
    return result


def load_findings_yaml(path: str | Path | None = None) -> dict[str, Any]:
    """Load and structurally validate the executable finding registry.

    PyYAML is used when available.  A constrained fallback keeps the core
    usable in the project's lightweight development environment while still
    rejecting malformed or unsupported registry entries.
    """

    registry_path = Path(path) if path is not None else resolve_runtime_resource("spec/findings.yaml")
    if not registry_path.is_file():
        raise FileNotFoundError(registry_path)
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        data = _fallback_yaml_load(registry_path)
    else:
        data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("findings registry root must be an object")
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ValueError("findings registry must contain a findings list")
    ids: set[str] = set()
    for index, entry in enumerate(findings):
        if not isinstance(entry, dict):
            raise ValueError(f"findings[{index}] must be an object")
        for key in ("id", "evaluator", "params", "side_mapping", "evidence"):
            if key not in entry:
                raise ValueError(f"findings[{index}] missing {key}")
        finding_id = entry["id"]
        if not isinstance(finding_id, str) or not finding_id:
            raise ValueError(f"findings[{index}].id must be a non-empty string")
        if finding_id in ids:
            raise ValueError(f"duplicate finding id: {finding_id}")
        ids.add(finding_id)
        if not isinstance(entry["evaluator"], str):
            raise ValueError(f"findings[{index}].evaluator must be a string")
        if not isinstance(entry["evidence"], dict):
            raise ValueError(f"findings[{index}].evidence must be an object")
    return data


def validate_findings_registry(
    data: dict[str, Any],
    *,
    evaluator_names: set[str] | None = None,
) -> list[str]:
    """Return human-readable registry errors instead of raising immediately."""

    errors: list[str] = []
    try:
        loaded = load_findings_yaml_from_data(data)
    except ValueError as exc:
        return [str(exc)]
    for entry in loaded["findings"]:
        evaluator = entry["evaluator"]
        if evaluator_names is not None and evaluator not in evaluator_names:
            errors.append(f"{entry['id']}: unknown evaluator {evaluator}")
    return errors


def load_findings_yaml_from_data(data: dict[str, Any]) -> dict[str, Any]:
    """Apply the same structural checks to already-loaded YAML data."""

    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        raise ValueError("findings registry must contain a findings list")
    ids: set[str] = set()
    for index, entry in enumerate(data["findings"]):
        if not isinstance(entry, dict):
            raise ValueError(f"findings[{index}] must be an object")
        missing = {"id", "evaluator", "params", "side_mapping", "evidence"} - entry.keys()
        if missing:
            raise ValueError(f"findings[{index}] missing {sorted(missing)[0]}")
        finding_id = entry["id"]
        if not isinstance(finding_id, str) or finding_id in ids:
            raise ValueError(f"invalid or duplicate finding id at index {index}")
        ids.add(finding_id)
    return data


__all__ = [
    "load_findings_yaml",
    "load_findings_yaml_from_data",
    "resolve_runtime_resource",
    "validate_findings_registry",
]
