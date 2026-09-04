from __future__ import annotations

"""Bilingual Markdown report rendering."""

import json
from typing import Any


def _evidence_line(evidence: dict[str, Any]) -> str:
    kind = evidence.get("type", "evidence")
    if kind == "frame":
        return (
            f"- `{evidence.get('ts')}` `[frame]` "
            f"{evidence.get('role', 'unknown')} {evidence.get('summary', '')} "
            f"({evidence.get('frame_ref', 'unknown')})"
        )
    return (
        f"- `{evidence.get('ts_start')}–{evidence.get('ts_end')}` "
        f"`[absence_window]` {evidence.get('summary', '')}; "
        f"coverage_ok={evidence.get('trace_coverage_ok')}"
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# FlashReport 分析报告 / Analysis Report",
        "",
        "## 元信息 / Metadata",
        "",
        f"- Source / 来源: `{report.get('source_file', '')}`",
        f"- Tool / 工具: `{report.get('tool', '')}` `{report.get('version', '')}`",
        f"- Schema / 版本: `{report.get('schema_version', '')}`",
        "",
        "## 结论摘要 / Conclusion",
        "",
    ]
    summary = report.get("summary") or {}
    first = report.get("first_deviation")
    if first:
        lines.extend(
            [
                f"- First deviation / 首个偏差: **{first.get('finding_id')}**",
                f"- Suspected side / 疑似责任侧: **{first.get('suspected_side')}**",
                f"- Confidence / 置信度: **{first.get('confidence', '').upper()}**",
                f"- Finding count / Finding 数量: `{summary.get('finding_count', 0)}`",
            ]
        )
    else:
        lines.append("- No finding was emitted / 未发现满足规则契约的 Finding")
    lines.extend(["", "## Findings 时间线 / Timeline", ""])
    findings = report.get("findings") or []
    if not findings:
        lines.append("No findings / 无 Finding。")
    for finding in findings:
        lines.extend(
            [
                f"### {finding.get('finding_id')} · {finding.get('category')}",
                "",
                f"- Deviation / 偏差时刻: `{finding.get('deviation_ts')}`",
                f"- Detected / 确认时刻: `{finding.get('detected_ts')}`",
                f"- Suspected side / 疑似责任侧: `{finding.get('suspected_side')}`",
                f"- Confidence / 置信度: `{finding.get('confidence')}`",
                f"- Observed / 观察: {finding.get('observed')}",
                f"- Expected / 预期: {finding.get('expected')}",
            ]
        )
        detail = finding.get("detail") or {}
        if detail:
            lines.append(f"- Detail / 细节: `{json.dumps(detail, ensure_ascii=False, sort_keys=True)}`")
        if finding.get("superseded_by"):
            lines.append(f"- Superseded by / 被覆盖原因: `{finding['superseded_by']}`")
        lines.extend(["", "Evidence / 证据:"])
        lines.extend(_evidence_line(evidence) for evidence in finding.get("evidence", []))
        lines.append("")

    lines.extend(
        [
            "## 建议 / Recommendation",
            "",
            "This report is an offline engineering aid. Validate conclusions against the original trace and the ECU/tester documentation before use in a vehicle or production workflow.",
            "本报告仅是离线工程辅助结果；用于车辆或生产流程前，必须结合原始 Trace 及 ECU/Tester 文档独立复核。",
            "",
            "## 附录：输入质量 / Appendix: Input Quality",
            "",
            "```json",
            json.dumps(report.get("input_stats") or {}, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = ["render_markdown"]
