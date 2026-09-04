from __future__ import annotations

"""Executable evaluator registry driven by ``spec/findings.yaml``."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..spec_utils import load_findings_yaml
from .flash_rules import oversize_or_bsc_error
from .transport_rules import (
    cf_after_cts_missing,
    missing_fc_after_block,
    missing_fc_after_ff,
    sn_gap,
    stmin_violation,
)
from .uds_rules import no_final_response


Evaluator = Callable[..., Any]


@dataclass(frozen=True)
class RuleSpec:
    finding_id: str
    evaluator: str
    params: dict[str, Any]
    side_mapping: dict[str, Any]
    evidence: dict[str, Any]
    confidence: str | None = None
    confidence_policy: str | None = None
    supersede: bool = False


RULE_EVALUATORS: dict[str, Evaluator] = {
    "missing_fc_after_ff": missing_fc_after_ff,
    "cf_after_cts_missing": cf_after_cts_missing,
    "sn_gap": sn_gap,
    "missing_fc_after_block": missing_fc_after_block,
    "stmin_violation": stmin_violation,
    "no_final_response": no_final_response,
    "oversize_or_bsc_error": oversize_or_bsc_error,
}


def load_rule_specs(path: str | Path | None = None) -> dict[str, RuleSpec]:
    """Load findings.yaml and reject unknown or unimplemented evaluators."""

    data = load_findings_yaml(path)
    specs: dict[str, RuleSpec] = {}
    for raw in data["findings"]:
        evaluator = raw["evaluator"]
        if evaluator not in RULE_EVALUATORS:
            raise ValueError(f"{raw['id']}: unknown evaluator {evaluator}")
        specs[raw["id"]] = RuleSpec(
            finding_id=raw["id"],
            evaluator=evaluator,
            params=dict(raw.get("params") or {}),
            side_mapping=dict(raw.get("side_mapping") or {}),
            evidence=dict(raw.get("evidence") or {}),
            confidence=raw.get("confidence"),
            confidence_policy=raw.get("confidence_policy"),
            supersede=bool(raw.get("supersede", False)),
        )
    return specs


def registry_consistency_errors(path: str | Path | None = None) -> list[str]:
    """Return consistency errors suitable for a spec gate test."""

    try:
        specs = load_rule_specs(path)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    errors: list[str] = []
    expected_ids = {
        "ISO-TP-001",
        "ISO-TP-002",
        "ISO-TP-003",
        "ISO-TP-004",
        "ISO-TP-005",
        "UDS-001",
        "FLASH-001",
    }
    if set(specs) != expected_ids:
        errors.append(f"finding ids mismatch: expected {sorted(expected_ids)}, got {sorted(specs)}")
    for finding_id, spec in specs.items():
        if spec.evaluator not in RULE_EVALUATORS:
            errors.append(f"{finding_id}: evaluator is not registered")
    return errors


__all__ = [
    "Evaluator",
    "RULE_EVALUATORS",
    "RuleSpec",
    "load_rule_specs",
    "registry_consistency_errors",
]
