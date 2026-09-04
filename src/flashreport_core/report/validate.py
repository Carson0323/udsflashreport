from __future__ import annotations

"""Report contract validation with an optional jsonschema fast path."""

import json
from pathlib import Path
from typing import Any

from ..models import ConfigValidationResult


_DEFAULT_SCHEMA = Path(__file__).resolve().parents[3] / "spec" / "report.schema.json"


def _basic_validate(report: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["root: expected object"]
    required = {
        "schema_version",
        "tool",
        "version",
        "source_file",
        "input_stats",
        "findings",
        "first_deviation",
        "summary",
    }
    errors.extend(f"root: missing required field {key}" for key in sorted(required - report.keys()))
    if report.get("schema_version") != "1.1":
        errors.append("schema_version: must be '1.1'")
    if not isinstance(report.get("findings"), list):
        errors.append("findings: expected array")
    else:
        for index, finding in enumerate(report["findings"]):
            if not isinstance(finding, dict):
                errors.append(f"findings[{index}]: expected object")
                continue
            finding_required = {
                "finding_id",
                "layer",
                "category",
                "deviation_ts",
                "detected_ts",
                "observed",
                "expected",
                "suspected_side",
                "confidence",
                "session",
                "service",
                "detail",
                "evidence",
                "superseded_by",
                "needs_normative_confirmation",
            }
            errors.extend(
                f"findings[{index}]: missing required field {key}"
                for key in sorted(finding_required - finding.keys())
            )
            evidence = finding.get("evidence")
            if not isinstance(evidence, list) or len(evidence) < 2:
                errors.append(f"findings[{index}].evidence: minimum 2 items")
    return errors


def validate_report(
    report: dict[str, Any],
    schema_path: str | Path | None = None,
) -> ConfigValidationResult:
    """Validate a report and return the same result shape as config validation."""

    errors = _basic_validate(report)
    if errors:
        return ConfigValidationResult(ok=False, errors=errors)
    path = Path(schema_path) if schema_path is not None else _DEFAULT_SCHEMA
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ConfigValidationResult(ok=False, errors=[f"schema: {exc}"])
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return ConfigValidationResult(ok=True, errors=[])
    try:
        jsonschema.Draft202012Validator(schema).validate(report)
    except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
        path_text = ".".join(str(item) for item in exc.absolute_path)
        return ConfigValidationResult(
            ok=False,
            errors=[f"{path_text or 'root'}: {exc.message}"],
        )
    return ConfigValidationResult(ok=True, errors=[])


__all__ = ["validate_report"]
