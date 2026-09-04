"""Run the public API against local-only injected private traces.

The input and all reports stay on the local machine. The runner deliberately
uses ``flashreport_core.api`` so BLF analysis is performed without an address
mapping file, leaving ambiguity visible for the human reviewer.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from flashreport_core import api


EXPECTED_FINDINGS: dict[str, set[str]] = {
    "cut_after_stage_timeout": {
        "UDS-001",
        "ISO-TP-001",
        "ISO-TP-002",
        "ISO-TP-003",
        "ISO-TP-004",
        "ISO-TP-005",
    },
    "missing_flow_control_timeout": {"ISO-TP-001", "ISO-TP-004"},
    # A non-pending NRC is intentionally represented by the public UDS
    # annotation contract, not converted into a new frozen Finding type.
    "ecu_negative_response": set(),
    "cf_sequence_violation": {"ISO-TP-003"},
}


def _run_variant(variant: dict[str, Any], report_root: Path) -> dict[str, Any]:
    analysis_input = Path(variant["analysis_input"])
    scenario = str(variant["scenario"])
    result: dict[str, Any] = {
        "scenario": scenario,
        "analysis_input": str(analysis_input),
        "injection_status": variant.get("status"),
        "passed": False,
    }
    started = time.perf_counter()
    try:
        if variant.get("status") != "INJECTED":
            raise AssertionError(f"injection was not applied: {variant.get('status')}")
        if not analysis_input.is_file():
            raise FileNotFoundError(analysis_input)
        config = api.default_config()
        bundle = api.load_trace(str(analysis_input), config)
        analysis = api.analyze_trace(bundle, config)
        report_dir = report_root / analysis_input.parent.name
        report_dir.mkdir(parents=True, exist_ok=True)
        stem = analysis_input.stem.replace(".analysis", "")
        markdown_path = report_dir / f"{stem}.md"
        json_path = report_dir / f"{stem}.json"
        exported = api.export_report(analysis, str(markdown_path), str(json_path))
        finding_ids = [finding.finding_id for finding in analysis.findings]
        expected = EXPECTED_FINDINGS.get(scenario, set())
        if scenario == "ecu_negative_response":
            expected_nrc = str(variant.get("operation", {}).get("nrc", ""))
            annotations = [
                annotation.uds_summary or ""
                for annotation in analysis.frame_annotations.values()
            ]
            matched = [summary for summary in annotations if f"NRC={expected_nrc}" in summary]
            if not matched:
                raise AssertionError(
                    f"scenario {scenario} produced no {expected_nrc} NRC annotation"
                )
        else:
            matched = sorted(expected.intersection(finding_ids))
            if not matched:
                raise AssertionError(
                    f"scenario {scenario} produced {finding_ids}; expected one of {sorted(expected)}"
                )
        result.update(
            {
                "passed": bool(exported["validated"]),
                "frame_count": len(bundle.frames),
                "conversation_count": len(bundle.conversations),
                "finding_count": len(analysis.findings),
                "finding_ids": finding_ids,
                "expected_match": matched,
                "first_deviation_id": (
                    analysis.first_deviation.finding_id if analysis.first_deviation else None
                ),
                "report_json": str(json_path),
                "report_markdown": str(markdown_path),
                "address_mapping": "default_auto_detect_without_manual_pairs",
            }
        )
        if not result["passed"]:
            raise AssertionError("report schema validation returned false")
    except Exception as exc:  # keep all variants in the report
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return result


def run(manifest_path: Path, output_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report_root = manifest_path.parent / "m7-verification-reports"
    report_root.mkdir(exist_ok=True)
    variants = [
        variant
        for source in manifest.get("sources", [])
        for variant in source.get("variants", [])
    ]
    results = [_run_variant(variant, report_root) for variant in variants]
    report = {
        "purpose": "local-only private corpus regression / 仅本机私有语料回归",
        "manifest": str(manifest_path),
        "network_upload": False,
        "config_mode": "default_config; no manual address mapping / 默认配置；无手工地址映射",
        "summary": {
            "variant_count": len(results),
            "passed_count": sum(bool(item["passed"]) for item in results),
            "failed_count": sum(not bool(item["passed"]) for item in results),
            "source_count": len(manifest.get("sources", [])),
        },
        "results": results,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local private corpus regression / 本机私有语料回归")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    report = run(args.manifest, args.output)
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0 if report["summary"]["failed_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
