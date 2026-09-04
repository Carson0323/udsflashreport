from __future__ import annotations

"""Registered UDS attribution evaluators."""

from ..models import WindowEvidence
from ..uds.pending import PendingIssue
from .context import RuleContext, build_finding, pdu_evidence, session_at


def no_final_response(issue: PendingIssue, ctx: RuleContext):
    transaction = ctx.transaction
    if transaction is None:
        return None
    request_ts = (
        transaction.pdu_req.ts_start
        if transaction.pdu_req is not None
        else (ctx.pending_timestamps[0] if ctx.pending_timestamps else issue.ts)
    )
    pending = bool(ctx.pending_timestamps)
    window_start = ctx.pending_timestamps[-1] if pending else request_ts
    covered = (
        window_start <= issue.ts <= ctx.trace_end_ts
        and ctx.quality.has_capture_gap is not True
        and ctx.quality.completeness in {"verified", "assumed"}
    )
    response_id = None
    if ctx.conversation is not None:
        response_frame = next(
            (
                frame
                for frame in ctx.conversation.ecu_to_tester_events[0:1]
                if frame.frame.can_id is not None
            ),
            None,
        )
        response_id = response_frame.frame.can_id if response_frame is not None else None
    evidence = pdu_evidence(
        transaction.pdu_req,
        f"UDS request 0x{transaction.request.sid:02X}"
        if transaction.request.sid is not None
        else "UDS request",
    )
    evidence.append(
        WindowEvidence(
            ts_start=window_start,
            ts_end=issue.ts,
            expected_role="ecu->tester",
            expected_kind="final UDS response",
            expected_can_id=response_id,
            matched_frame_count=0,
            trace_coverage_ok=covered,
            summary=(
                "No final response before P2* deadline"
                if pending
                else "No final response before P2 deadline"
            ),
        )
    )
    timing = ctx.timing.uds_p2_star if pending else ctx.timing.uds_p2
    return build_finding(
        ctx=ctx,
        finding_id="UDS-001",
        layer="UDS",
        category="no_final_response",
        deviation_ts=issue.ts,
        detected_ts=max(issue.ts, ctx.trace_end_ts),
        observed=issue.observed,
        expected=issue.expected,
        suspected_side="ecu",
        base_confidence="high",
        detail={
            "timeout_ms": timing.value_ms,
            "timing_source": timing.source,
            "pending_count": len(transaction.pending_events),
            "deadline_ts": issue.ts,
        },
        evidence=evidence,
        session=session_at(ctx.sessions, request_ts),
        service=transaction.request.service_name,
        timing_source=timing.source,
        window_covered=covered,
    )


def negative_response(_issue, ctx: RuleContext):
    """Emit an evidence-backed Finding for a final ECU NRC response."""

    transaction = ctx.transaction
    if transaction is None or transaction.final_response is None:
        return None
    response = transaction.final_response
    if response.is_positive is not False or response.pending:
        return None
    request_ts = (
        transaction.pdu_req.ts_start
        if transaction.pdu_req is not None
        else ctx.trace_end_ts
    )
    response_ts = (
        transaction.pdu_resp.ts_start
        if transaction.pdu_resp is not None
        else request_ts
    )
    evidence = pdu_evidence(
        transaction.pdu_req,
        f"UDS request 0x{transaction.request.sid:02X}"
        if transaction.request.sid is not None
        else "UDS request",
    )
    evidence.extend(
        pdu_evidence(
            transaction.pdu_resp,
            f"ECU negative response NRC=0x{response.nrc:02X}"
            if response.nrc is not None
            else "ECU negative response",
        )
    )
    if len(evidence) < 2:
        return None
    service = transaction.request.service_name or "unknown service"
    return build_finding(
        ctx=ctx,
        finding_id="UDS-002",
        layer="UDS",
        category="ecu_negative_response",
        deviation_ts=response_ts,
        detected_ts=response_ts,
        observed=(
            f"ECU returned NRC=0x{response.nrc:02X} "
            f"({response.nrc_text or 'unknownNRC'})"
            if response.nrc is not None
            else "ECU returned a malformed negative response"
        ),
        expected=f"Positive response for {service}",
        suspected_side="ecu",
        base_confidence="high",
        detail={
            "request_sid": transaction.request.sid,
            "service": service,
            "nrc": response.nrc,
            "nrc_name": response.nrc_text,
            "request_raw": transaction.request.raw.hex().upper(),
            "response_raw": response.raw.hex().upper(),
            "request_frame_ref": transaction.pdu_req.frames[0].frame_ref
            if transaction.pdu_req and transaction.pdu_req.frames
            else None,
            "response_frame_ref": transaction.pdu_resp.frames[0].frame_ref
            if transaction.pdu_resp and transaction.pdu_resp.frames
            else None,
        },
        evidence=evidence,
        session=session_at(ctx.sessions, request_ts),
        service=transaction.request.service_name,
    )


__all__ = ["negative_response", "no_final_response"]
