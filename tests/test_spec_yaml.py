from __future__ import annotations

import pytest

import flashreport_core.spec_utils as spec_utils
from flashreport_core.rules.registry import (
    RULE_EVALUATORS,
    load_rule_specs,
    registry_consistency_errors,
)
from flashreport_core.spec_utils import load_findings_yaml


def test_findings_yaml_and_registry_are_consistent() -> None:
    raw = load_findings_yaml()
    specs = load_rule_specs()

    assert len(raw["findings"]) == 7
    assert set(specs) == {
        "ISO-TP-001",
        "ISO-TP-002",
        "ISO-TP-003",
        "ISO-TP-004",
        "ISO-TP-005",
        "UDS-001",
        "FLASH-001",
    }
    assert registry_consistency_errors() == []


def test_unknown_evaluator_is_rejected(tmp_path) -> None:
    path = tmp_path / "findings.yaml"
    path.write_text(
        """schema_version: '1.1'
default_confidence_policy: window_and_timing
findings:
  - id: TEST-001
    evaluator: unknown_rule
    params: {}
    side_mapping: {}
    evidence: { min_count: 2, allowed_types: [frame] }
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown evaluator"):
        load_rule_specs(path)


def test_runtime_resource_resolves_frozen_package_root(tmp_path, monkeypatch) -> None:
    packaged_spec = tmp_path / "spec" / "findings.yaml"
    packaged_spec.parent.mkdir()
    packaged_spec.write_text("findings: []\n", encoding="utf-8")
    monkeypatch.setattr(spec_utils.sys, "frozen", True, raising=False)
    monkeypatch.setattr(spec_utils.sys, "_MEIPASS", str(tmp_path), raising=False)

    assert spec_utils.resolve_runtime_resource("spec/findings.yaml") == packaged_spec
