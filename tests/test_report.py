from __future__ import annotations

import json

import pytest

from flashreport_core.api import analyze_trace, default_config, export_report, load_trace
from flashreport_core.report.markdown import render_markdown
from flashreport_core.report.validate import validate_report


def test_report_export_is_bilingual_and_schema_valid(tmp_path) -> None:
    cfg = default_config()
    result = analyze_trace(load_trace("samples/success_full_download.asc", cfg), cfg)
    md_path = tmp_path / "report.md"
    json_path = tmp_path / "report.json"

    exported = export_report(result, str(md_path), str(json_path))

    assert exported["validated"] is True
    assert md_path.is_file()
    assert json_path.is_file()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert validate_report(report).ok
    markdown = md_path.read_text(encoding="utf-8")
    assert "分析报告" in markdown
    assert "Analysis Report" in markdown


def test_invalid_report_is_rejected_before_writing(tmp_path) -> None:
    cfg = default_config()
    result = analyze_trace(load_trace("samples/success_full_download.asc", cfg), cfg)
    result.report_data["schema_version"] = "invalid"
    md_path = tmp_path / "invalid.md"
    json_path = tmp_path / "invalid.json"

    assert not validate_report(result.report_data).ok
    with pytest.raises(ValueError, match="invalid report"):
        export_report(result, str(md_path), str(json_path))
    assert not md_path.exists()
    assert not json_path.exists()


def test_report_renderer_handles_finding_timeline() -> None:
    report = {
        "source_file": "trace.asc",
        "tool": "udsflashreport",
        "version": "test",
        "schema_version": "1.1",
        "summary": {"finding_count": 0},
        "input_stats": {},
        "findings": [],
        "first_deviation": None,
    }
    assert "未发现" in render_markdown(report)
