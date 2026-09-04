from __future__ import annotations

"""Deterministic attribution orchestration for the M4 milestone."""

from dataclasses import fields, is_dataclass
from typing import Any, Iterable

from .. import __version__
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
from ..workflow import build_workflow_steps


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
        "UDS-002": "uds_002",
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
    if not (_enabled(cfg, "UDS-001") or _enabled(cfg, "UDS-002")):
        return []
    findings: list[Finding] = []
    for index, transaction in enumerate(transactions):
        request_ts = _request_ts(transaction, float(index))
        timing = resolve_timing(cfg, _server_timing_before(conversation, request_ts))
        context = RuleContext(
            conversation=conversation,
            quality=quality,
            trace_end_ts=quality.end_ts,
            timing=timing,
            transactions=transactions,
            sessions=sessions,
            transaction=transaction,
            ambiguous=ambiguous or transaction.ambiguous,
            session_name=session_at(sessions, request_ts),
        )
        if _enabled(cfg, "UDS-002") and transaction.final_response is not None:
            negative_spec = specs["UDS-002"]
            negative = RULE_EVALUATORS[negative_spec.evaluator](None, context)
            if negative is not None and _evidence_contract_ok(negative, negative_spec):
                findings.append(negative)
        if not _enabled(cfg, "UDS-001"):
            continue
        spec = specs["UDS-001"]
        evaluator = RULE_EVALUATORS[spec.evaluator]
        issue, pending_timestamps, request_ts = _transaction_pending_issue(
            conversation,
            transaction,
            timing,
            quality.end_ts,
            index,
        )
        if issue is None:
            continue
        pending_context = RuleContext(
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
        finding = evaluator(issue, pending_context)
        if finding is not None and _evidence_contract_ok(finding, spec):
            findings.append(finding)
    if _enabled(cfg, "UDS-002"):
        negative_spec = specs["UDS-002"]
        negative_evaluator = RULE_EVALUATORS[negative_spec.evaluator]
        for transaction in _orphan_negative_transactions(conversation, transactions):
            request_ts = _request_ts(transaction, 0.0)
            context = RuleContext(
                conversation=conversation,
                quality=quality,
                trace_end_ts=quality.end_ts,
                timing=resolve_timing(cfg, _server_timing_before(conversation, request_ts)),
                transactions=transactions,
                sessions=sessions,
                transaction=transaction,
                ambiguous=True,
                session_name=session_at(sessions, request_ts),
            )
            finding = negative_evaluator(None, context)
            if finding is not None:
                finding.detail["match_status"] = "orphan_negative_response"
                finding.detail["review_note"] = (
                    "The ECU NRC was captured without an outstanding request; "
                    "the nearest preceding request for the referenced SID was used."
                )
            if finding is not None and _evidence_contract_ok(finding, negative_spec):
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


def _message_details(message) -> dict[str, object]:
    details = {
        "sid": message.sid,
        "service_name": message.service_name,
        "subfunction": message.subfunction,
        "did": message.did,
        "block_seq": message.block_seq,
        "max_block_length": message.max_block_length,
        "is_positive": message.is_positive,
        "nrc": message.nrc,
        "nrc_name": message.nrc_text,
        "pending": message.pending,
        "raw": " ".join(f"{value:02X}" for value in message.raw) or "—",
    }
    raw = bytes(message.raw)
    if message.sid == 0x34 and len(raw) >= 3:
        address_size = (raw[2] >> 4) & 0x0F
        length_size = raw[2] & 0x0F
        length_start = 3 + address_size
        if address_size and length_size and len(raw) >= length_start + length_size:
            details["start_address"] = int.from_bytes(raw[3:length_start], "big")
            details["transfer_length"] = int.from_bytes(
                raw[length_start : length_start + length_size], "big"
            )
    if message.sid == 0x31 and len(raw) >= 4:
        details["routine_id"] = int.from_bytes(raw[2:4], "big")
        details["routine_parameters"] = " ".join(f"{value:02X}" for value in raw[4:]) or "—"
        details["routine_ascii"] = "".join(
            chr(value) if 0x20 <= value <= 0x7E else "." for value in raw[4:]
        ) or "—"
    if message.sid in {0x22, 0x2E, 0x62, 0x6E} and len(raw) >= 3:
        details["did_bytes"] = " ".join(f"{value:02X}" for value in raw[1:3])
    if message.sid in {0x2E, 0x6E} and len(raw) > 3:
        details["write_data"] = " ".join(f"{value:02X}" for value in raw[3:])
        details["write_ascii"] = "".join(
            chr(value) if 0x20 <= value <= 0x7E else "." for value in raw[3:]
        ) or "—"
    if message.sid in {0x22, 0x62} and len(raw) > 3:
        details["read_data"] = " ".join(f"{value:02X}" for value in raw[3:])
        details["read_ascii"] = "".join(
            chr(value) if 0x20 <= value <= 0x7E else "." for value in raw[3:]
        ) or "—"
    return details


def _functional_payload(data: bytes) -> bytes | None:
    if not data:
        return None
    pci_type = data[0] >> 4
    if pci_type == 0x0:
        length = data[0] & 0x0F
        return data[1 : 1 + length] if length and len(data) >= length + 1 else None
    if pci_type == 0x1 and len(data) >= 3:
        return data[2:]
    return None


def _annotate_uds(bundle: TraceBundle, cfg: AppConfig) -> dict[str, FrameAnnotation]:
    annotations = dict(bundle.frame_annotations)
    for conversation in bundle.conversations:
        match = match_conversation(
            conversation,
            timing=cfg.timeouts,
            trace_end_ts=bundle.quality.end_ts,
        )
        sessions = reconstruct_sessions(match.transactions)
        for pdu in conversation.pdus:
            message = decode_uds(pdu)
            summary = _uds_summary(pdu)
            details = _message_details(message)
            session = session_at(sessions, pdu.ts_start)
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
                    addressing_mode=previous.addressing_mode,
                    uds_details={**previous.uds_details, **details, "session": session},
                )
    for frame in bundle.frames:
        previous = annotations.get(frame.frame_ref)
        if previous is None or previous.addressing_mode != "functional":
            continue
        payload = _functional_payload(frame.data)
        if payload is None:
            continue
        message = decode_uds(payload)
        if message.sid is None:
            continue
        annotations[frame.frame_ref] = FrameAnnotation(
            frame_ref=previous.frame_ref,
            direction=previous.direction,
            isotp_summary=previous.isotp_summary,
            uds_summary=_uds_summary_from_message(message),
            summary=" | ".join(
                value for value in (previous.isotp_summary, _uds_summary_from_message(message)) if value
            ),
            addressing_mode=previous.addressing_mode,
            uds_details={**previous.uds_details, **_message_details(message)},
        )
    return annotations


def _uds_summary_from_message(message) -> str:
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


def _orphan_negative_transactions(
    conversation: IsoTpConversation,
    transactions: list[UdsTransaction],
) -> list[UdsTransaction]:
    """Retain a locatable Finding when a capture contains an unpaired NRC.

    Some injected and real captures contain an ECU negative response after the
    request has already been closed by a positive response.  The matcher
    correctly marks that response as unpaired; for reporting, associate it with
    the nearest preceding request for the service named in byte 2 of 0x7F.
    The transaction is marked ambiguous so the UI communicates that this is a
    reviewable association rather than a silent certainty.
    """

    attached_response_refs = {
        frame.frame_ref
        for transaction in transactions
        if transaction.pdu_resp is not None
        for frame in transaction.pdu_resp.frames
    }
    requests = [
        (pdu, decode_uds(pdu))
        for pdu in conversation.pdus
        if pdu.direction == "tester->ecu" and decode_uds(pdu).sid is not None
    ]
    orphaned: list[UdsTransaction] = []
    for response_pdu in conversation.pdus:
        if response_pdu.direction != "ecu->tester":
            continue
        if any(frame.frame_ref in attached_response_refs for frame in response_pdu.frames):
            continue
        response = decode_uds(response_pdu)
        if response.sid != 0x7F or len(response.raw) < 2:
            continue
        target_sid = response.raw[1]
        preceding = [
            (pdu, message)
            for pdu, message in requests
            if pdu.ts_start <= response_pdu.ts_start and message.sid == target_sid
        ]
        if not preceding:
            continue
        request_pdu, request = preceding[-1]
        orphaned.append(
            UdsTransaction(
                request=request,
                pending_events=[],
                final_response=response,
                pdu_req=request_pdu,
                pdu_resp=response_pdu,
                ambiguous=True,
            )
        )
    return orphaned


def analyze_bundle(
    bundle: TraceBundle,
    cfg: AppConfig,
    *,
    findings_path: str | None = None,
) -> AnalysisResult:
    """Analyze loaded conversations and return findings plus GUI projections."""

    specs = load_rule_specs(findings_path)
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
    workflow_steps = build_workflow_steps(bundle, cfg)
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
        "version": __version__,
        "source_file": bundle.path,
        "input_stats": _json_value(input_stats),
        "findings": [finding_to_dict(finding) for finding in findings],
        "first_deviation": finding_to_dict(first_deviation) if first_deviation else None,
        "summary": {
            "finding_count": len(findings),
            "first_deviation_id": first_deviation.finding_id if first_deviation else None,
        },
        "workflow": _json_value(workflow_steps),
    }
    return AnalysisResult(
        bundle=bundle,
        findings=findings,
        first_deviation=first_deviation,
        report_data=report_data,
        frame_annotations=_annotate_uds(bundle, cfg),
        workflow_steps=workflow_steps,
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
