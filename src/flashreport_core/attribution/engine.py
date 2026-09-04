from __future__ import annotations

"""Deterministic attribution orchestration for the M4 milestone."""

from dataclasses import fields, is_dataclass
from typing import Any, Iterable

from ..config import timeout_provenance
from ..isotp.validator import validate_conversation
from ..models import (
    AnalysisResult,
    AppConfig,
    Finding,
    FrameAnnotation,
    IsoTpConversation,
    IsoTpPdu,
    ResolvedTimingConfig,
    ResolvedTimingValue,
    TraceBundle,
    TimeoutsConfig,
    UdsTransaction,
)
from ..session.diagnostic import reconstruct_sessions
from ..session.flash import reconstruct_flash_sessions
from ..uds.decoder import decode_uds, extract_server_timing
from ..uds.pending import PendingIssue, check_pending
from ..uds.transaction_matcher import match_conversation
from ..rules.context import RuleContext, session_at
from ..rules.registry import RULE_EVALUATORS, RuleSpec, load_rule_specs


TRANSPORT_FINDING_IDS = {
    "missing_fc_after_ff": "ISO-TP-001",
    "cf_after_cts_missing": "ISO-TP-002",
    "sn_gap": "ISO-TP-003",
    "missing_fc_after_block": "ISO-TP-004",
    "stmin_violation": "ISO-TP-005",
}


def resolve_timing(
    cfg: AppConfig,
    server_timing=None,
) -> ResolvedTimingConfig:
    """Resolve values and provenance once before invoking evaluators."""

    provenance = timeout_provenance(cfg)
    return ResolvedTimingConfig(
        isotp_fc=ResolvedTimingValue(
            value_ms=cfg.timeouts.isotp_fc_ms,
            source=provenance.isotp_fc,
        ),
        isotp_cf=ResolvedTimingValue(
            value_ms=cfg.timeouts.isotp_cf_ms,
            source=provenance.isotp_cf,
        ),
        uds_p2=ResolvedTimingValue(
            value_ms=server_timing.p2_ms
            if server_timing is not None
            else cfg.timeouts.uds_p2_ms,
            source="observed_server" if server_timing is not None else provenance.uds_p2,
        ),
        uds_p2_star=ResolvedTimingValue(
            value_ms=server_timing.p2_star_ms
            if server_timing is not None
            else cfg.timeouts.uds_p2_star_ms,
            source="observed_server"
            if server_timing is not None
            else provenance.uds_p2_star,
        ),
    )


def _timeouts(timing: ResolvedTimingConfig) -> TimeoutsConfig:
    return TimeoutsConfig(
        isotp_fc_ms=timing.isotp_fc.value_ms,
        isotp_cf_ms=timing.isotp_cf.value_ms,
        uds_p2_ms=timing.uds_p2.value_ms,
        uds_p2_star_ms=timing.uds_p2_star.value_ms,
    )


def _request_ts(transaction: UdsTransaction, fallback: float) -> float:
    return transaction.pdu_req.ts_start if transaction.pdu_req is not None else fallback


def _response_items(conversation: IsoTpConversation) -> list[tuple[float, Any, IsoTpPdu]]:
    return [
        (pdu.ts_start, decode_uds(pdu), pdu)
        for pdu in sorted(conversation.pdus, key=lambda item: item.ts_start)
        if pdu.direction == "ecu->tester"
    ]


def _server_timing_before(conversation: IsoTpConversation, request_ts: float):
    candidates = []
    for ts, message, _pdu in _response_items(conversation):
        if ts > request_ts or message.sid != 0x50:
            continue
        timing = extract_server_timing(message)
        if timing is not None:
            candidates.append((ts, timing))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _pending_timestamps(
    conversation: IsoTpConversation,
    transaction: UdsTransaction,
    request_ts: float,
) -> list[float]:
    if not transaction.pending_events:
        return []
    final_ts = transaction.pdu_resp.ts_start if transaction.pdu_resp is not None else None
    candidates = [
        (ts, message.raw)
        for ts, message, _pdu in _response_items(conversation)
        if ts >= request_ts
        and (final_ts is None or ts <= final_ts)
        and message.pending
    ]
    used: set[int] = set()
    timestamps: list[float] = []
    for pending in transaction.pending_events:
        match_index = next(
            (
                index
                for index, (ts, raw) in enumerate(candidates)
                if index not in used and raw == pending.raw
            ),
            None,
        )
        if match_index is None:
            continue
        used.add(match_index)
        timestamps.append(candidates[match_index][0])
    return timestamps


def _transaction_pending_issue(
    conversation: IsoTpConversation,
    transaction: UdsTransaction,
    timing: ResolvedTimingConfig,
    trace_end_ts: float,
    index: int,
) -> tuple[PendingIssue | None, list[float], float]:
    request_ts = _request_ts(transaction, float(index))
    # UDS-001 is the no-final-response finding.  A late final response may be
    # useful to a future timing-quality rule, but it is not a missing-final
    # finding and must not turn an otherwise successful flash trace into one.
    if transaction.final_response is not None:
        return None, [], request_ts
    pending_timestamps = _pending_timestamps(conversation, transaction, request_ts)
    pending_values = [
        (ts, message)
        for ts, message in zip(pending_timestamps, transaction.pending_events)
    ]
    issue = check_pending(
        request_ts,
        pending_values,
        _timeouts(timing),
        final_ts=(transaction.pdu_resp.ts_start if transaction.pdu_resp is not None else None),
        trace_end_ts=trace_end_ts,
    )
    return issue, pending_timestamps, request_ts


def _enabled(cfg: AppConfig, finding_id: str) -> bool:
    field_name = {
        "ISO-TP-001": "iso_tp_001",
        "ISO-TP-002": "iso_tp_002",
        "ISO-TP-003": "iso_tp_003",
        "ISO-TP-004": "iso_tp_004",
        "ISO-TP-005": "iso_tp_005",
        "UDS-001": "uds_001",
        "FLASH-001": "flash_001",
    }[finding_id]
    return bool(getattr(cfg.rules, field_name))


def _window_covered(finding: Finding) -> bool:
    return all(
        getattr(evidence, "trace_coverage_ok", True)
        for evidence in finding.evidence
        if getattr(evidence, "type", None) == "absence_window"
    )


def _evidence_contract_ok(finding: Finding, spec: RuleSpec) -> bool:
    policy = spec.evidence
    minimum = int(policy.get("min_count", 2))
    if len(finding.evidence) < minimum:
        return False
    types = [getattr(evidence, "type", None) for evidence in finding.evidence]
    required = set(policy.get("required_types", []))
    allowed = set(policy.get("allowed_types", []))
    if required and not required.issubset(types):
        return False
    if allowed and not set(types).issubset(allowed):
        return False
    return True


def _run_transport_rules(
    *,
    conversation: IsoTpConversation,
    transactions: list[UdsTransaction],
    sessions: list[Any],
    cfg: AppConfig,
    specs: dict[str, RuleSpec],
    ambiguous: bool,
    quality,
) -> list[Finding]:
    findings: list[Finding] = []
    timing = resolve_timing(cfg)
    issues = validate_conversation(conversation, cfg.timeouts, quality)
    for issue in issues:
        finding_id = TRANSPORT_FINDING_IDS.get(issue.kind)
        if finding_id is None or not _enabled(cfg, finding_id):
            continue
        spec = specs[finding_id]
        evaluator = RULE_EVALUATORS[spec.evaluator]
        context = RuleContext(
            conversation=conversation,
            quality=quality,
            trace_end_ts=quality.end_ts,
            timing=timing,
            issue=issue,
            transactions=transactions,
            sessions=sessions,
            ambiguous=ambiguous,
            session_name=session_at(sessions, issue.ts),
        )
        finding = evaluator(issue, context)
        if finding is not None and _evidence_contract_ok(finding, spec):
            findings.append(finding)
    return findings


def _run_uds_rule(
    *,
    conversation: IsoTpConversation,
    transactions: list[UdsTransaction],
    sessions: list[Any],
    cfg: AppConfig,
    specs: dict[str, RuleSpec],
    ambiguous: bool,
    quality,
) -> list[Finding]:
    if not _enabled(cfg, "UDS-001"):
        return []
    spec = specs["UDS-001"]
    evaluator = RULE_EVALUATORS[spec.evaluator]
    findings: list[Finding] = []
    for index, transaction in enumerate(transactions):
        request_ts = _request_ts(transaction, float(index))
        timing = resolve_timing(cfg, _server_timing_before(conversation, request_ts))
        issue, pending_timestamps, request_ts = _transaction_pending_issue(
            conversation,
            transaction,
            timing,
            quality.end_ts,
            index,
        )
        if issue is None:
            continue
        context = RuleContext(
            conversation=conversation,
            quality=quality,
            trace_end_ts=quality.end_ts,
            timing=timing,
            issue=issue,
            transactions=transactions,
            sessions=sessions,
            transaction=transaction,
            pending_timestamps=pending_timestamps,
            ambiguous=ambiguous or transaction.ambiguous,
            session_name=session_at(sessions, request_ts),
        )
        finding = evaluator(issue, context)
        if finding is not None and _evidence_contract_ok(finding, spec):
            findings.append(finding)
    return findings


def _run_flash_rule(
    *,
    conversations: Iterable[IsoTpConversation],
    transaction_sets: dict[str, list[UdsTransaction]],
    sessions_by_pair: dict[str, list[Any]],
    cfg: AppConfig,
    specs: dict[str, RuleSpec],
    quality,
) -> list[Finding]:
    if not _enabled(cfg, "FLASH-001"):
        return []
    spec = specs["FLASH-001"]
    evaluator = RULE_EVALUATORS[spec.evaluator]
    findings: list[Finding] = []
    for conversation in conversations:
        transactions = transaction_sets.get(conversation.pair_key, [])
        for flash_session in reconstruct_flash_sessions(transactions):
            for block in flash_session.blocks:
                request_ts = _request_ts(block.transaction, flash_session.start_ts or 0.0)
                context = RuleContext(
                    conversation=conversation,
                    quality=quality,
                    trace_end_ts=quality.end_ts,
                    timing=resolve_timing(cfg),
                    transactions=transactions,
                    sessions=sessions_by_pair.get(conversation.pair_key, []),
                    flash_session=flash_session,
                    flash_block=block,
                    ambiguous=block.transaction.ambiguous,
                    session_name=session_at(
                        sessions_by_pair.get(conversation.pair_key, []), request_ts
                    ),
                )
                finding = evaluator(None, context)
                if finding is not None and _evidence_contract_ok(finding, spec):
                    findings.append(finding)
    return findings


def _mark_superseded(findings: list[Finding]) -> None:
    tester_findings = sorted(
        (
            finding
            for finding in findings
            if finding.suspected_side == "tester"
            and finding.finding_id != "UDS-001"
        ),
        key=lambda finding: (finding.deviation_ts, finding.detected_ts, finding.finding_id),
    )
    for finding in findings:
        if finding.finding_id != "UDS-001":
            continue
        earlier = next(
            (
                candidate
                for candidate in tester_findings
                if candidate.deviation_ts < finding.deviation_ts
                and candidate.detail.get("pair_key") == finding.detail.get("pair_key")
            ),
            None,
        )
        if earlier is not None:
            finding.superseded_by = earlier.finding_id


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex().upper()
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def finding_to_dict(finding: Finding) -> dict[str, Any]:
    return _json_value(finding)


def _uds_summary(pdu: IsoTpPdu) -> str:
    message = decode_uds(pdu)
    if message.sid is None:
        return "UDS malformed/empty"
    summary = f"0x{message.sid:02X} {message.service_name or 'unknown'}"
    if message.block_seq is not None:
        summary += f" BSC={message.block_seq}"
    if message.nrc is not None:
        summary += f" NRC=0x{message.nrc:02X}"
    if message.pending:
        summary += " pending"
    return summary


def _annotate_uds(bundle: TraceBundle) -> dict[str, FrameAnnotation]:
    annotations = dict(bundle.frame_annotations)
    for conversation in bundle.conversations:
        for pdu in conversation.pdus:
            summary = _uds_summary(pdu)
            for frame in pdu.frames:
                previous = annotations.get(frame.frame_ref)
                if previous is None:
                    continue
                combined = " | ".join(
                    value for value in (previous.isotp_summary, summary) if value
                )
                annotations[frame.frame_ref] = FrameAnnotation(
                    frame_ref=previous.frame_ref,
                    direction=previous.direction,
                    isotp_summary=previous.isotp_summary,
                    uds_summary=summary,
                    summary=combined or previous.summary,
                )
    return annotations


def analyze_bundle(bundle: TraceBundle, cfg: AppConfig) -> AnalysisResult:
    """Analyze loaded conversations and return findings plus GUI projections."""

    specs = load_rule_specs()
    findings: list[Finding] = []
    transaction_sets: dict[str, list[UdsTransaction]] = {}
    sessions_by_pair: dict[str, list[Any]] = {}
    ambiguous_pairs: list[str] = []
    transport_issue_count = 0

    for conversation in bundle.conversations:
        match = match_conversation(
            conversation,
            timing=cfg.timeouts,
            trace_end_ts=bundle.quality.end_ts,
        )
        transactions = match.transactions
        transaction_sets[conversation.pair_key] = transactions
        sessions = reconstruct_sessions(transactions)
        sessions_by_pair[conversation.pair_key] = sessions
        ambiguous = match.ambiguous
        if ambiguous:
            ambiguous_pairs.append(conversation.pair_key)
        transport_issue_count += len(validate_conversation(conversation, cfg.timeouts, bundle.quality))
        findings.extend(
            _run_transport_rules(
                conversation=conversation,
                transactions=transactions,
                sessions=sessions,
                cfg=cfg,
                specs=specs,
                ambiguous=ambiguous,
                quality=bundle.quality,
            )
        )
        findings.extend(
            _run_uds_rule(
                conversation=conversation,
                transactions=transactions,
                sessions=sessions,
                cfg=cfg,
                specs=specs,
                ambiguous=ambiguous,
                quality=bundle.quality,
            )
        )

    findings.extend(
        _run_flash_rule(
            conversations=bundle.conversations,
            transaction_sets=transaction_sets,
            sessions_by_pair=sessions_by_pair,
            cfg=cfg,
            specs=specs,
            quality=bundle.quality,
        )
    )
    findings.sort(key=lambda finding: (finding.deviation_ts, finding.detected_ts, finding.finding_id))
    _mark_superseded(findings)
    first_deviation = next(
        (
            finding
            for finding in findings
            if finding.superseded_by is None
        ),
        None,
    )

    input_stats = dict(bundle.input_stats)
    input_stats.setdefault(
        "trace_quality",
        {
            "start_ts": bundle.quality.start_ts,
            "end_ts": bundle.quality.end_ts,
            "has_capture_gap": bundle.quality.has_capture_gap,
            "dropped_frame_count": bundle.quality.dropped_frame_count,
            "source_channels": bundle.quality.source_channels,
            "filter_state_known": bundle.quality.filter_state_known,
            "completeness": bundle.quality.completeness,
        },
    )
    input_stats.setdefault("unsupported", [])
    input_stats.setdefault("unsupported_count", 0)
    input_stats.update(
        {
            "ambiguous": bool(ambiguous_pairs),
            "ambiguous_count": len(ambiguous_pairs),
            "ambiguous_pairs": ambiguous_pairs,
            "transport_issue_count": transport_issue_count,
            "finding_count": len(findings),
        }
    )
    report_data = {
        "schema_version": "1.1",
        "tool": "udsflashreport",
        "version": "0.1.0.dev0",
        "source_file": bundle.path,
        "input_stats": _json_value(input_stats),
        "findings": [finding_to_dict(finding) for finding in findings],
        "first_deviation": finding_to_dict(first_deviation) if first_deviation else None,
        "summary": {
            "finding_count": len(findings),
            "first_deviation_id": first_deviation.finding_id if first_deviation else None,
        },
    }
    return AnalysisResult(
        bundle=bundle,
        findings=findings,
        first_deviation=first_deviation,
        report_data=report_data,
        frame_annotations=_annotate_uds(bundle),
        conversation_summaries=bundle.conversation_summaries,
    )


attribute_trace = analyze_bundle
analyze = analyze_bundle


__all__ = [
    "analyze",
    "analyze_bundle",
    "attribute_trace",
    "finding_to_dict",
    "resolve_timing",
]
