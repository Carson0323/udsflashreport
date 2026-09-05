from __future__ import annotations

"""Registered ISO-TP attribution evaluators."""

from ..models import FrameEvidence, TransportIssue
from .context import (
    RuleContext,
    build_finding,
    issue_window_covered,
    receiver_side,
    sender_side,
    session_at,
)


def _first_frame(issue: TransportIssue) -> FrameEvidence | None:
    return next((item for item in issue.evidence if isinstance(item, FrameEvidence)), None)


def _anchor_ts(issue: TransportIssue) -> float:
    """Return the frame where the violation became possible.

    ``TransportIssue.ts`` is the observation/deadline timestamp for absence
    rules.  The user-facing deviation must instead point to the FF, CTS, or
    last CF that started the violated waiting interval.
    """

    frame = _first_frame(issue)
    return frame.ts if frame is not None else issue.ts


def missing_fc_after_ff(issue: TransportIssue, ctx: RuleContext):
    frame = _first_frame(issue)
    deviation_ts = _anchor_ts(issue)
    role = frame.role if frame is not None else None
    side = receiver_side(role)
    source = ctx.timing.isotp_fc.source
    return build_finding(
        ctx=ctx,
        finding_id="ISO-TP-001",
        layer="ISO-TP",
        category="missing_fc_after_ff",
        deviation_ts=deviation_ts,
        detected_ts=issue.ts,
        observed=issue.observed,
        expected=issue.expected,
        suspected_side=side,
        base_confidence="high",
        detail={
            "timeout_ms": ctx.timing.isotp_fc.value_ms,
            "timing_source": source,
            "anchor_ts": deviation_ts,
            "deadline_ts": issue.ts,
        },
        evidence=list(issue.evidence),
        session=session_at(ctx.sessions, deviation_ts),
        timing_source=source,
        window_covered=issue_window_covered(issue),
    )


def cf_after_cts_missing(issue: TransportIssue, ctx: RuleContext):
    window_role = next(
        (
            item.expected_role
            for item in issue.evidence
            if getattr(item, "type", None) == "absence_window"
        ),
        None,
    )
    side = sender_side(window_role)
    deviation_ts = _anchor_ts(issue)
    source = ctx.timing.isotp_cf.source
    return build_finding(
        ctx=ctx,
        finding_id="ISO-TP-002",
        layer="ISO-TP",
        category="cf_after_cts_missing",
        deviation_ts=deviation_ts,
        detected_ts=issue.ts,
        observed=issue.observed,
        expected=issue.expected,
        suspected_side=side,
        base_confidence="high",
        detail={
            "timeout_ms": ctx.timing.isotp_cf.value_ms,
            "timing_source": source,
            "anchor_ts": deviation_ts,
            "deadline_ts": issue.ts,
        },
        evidence=list(issue.evidence),
        session=session_at(ctx.sessions, deviation_ts),
        timing_source=source,
        window_covered=issue_window_covered(issue),
    )


def sn_gap(issue: TransportIssue, ctx: RuleContext):
    bad = _first_frame(issue)
    evidence = list(issue.evidence)
    if bad is not None and ctx.conversation is not None:
        events = sorted(
            ctx.conversation.tester_to_ecu_events + ctx.conversation.ecu_to_tester_events,
            key=lambda event: event.ts,
        )
        previous = next(
            (
                event.frame
                for event in reversed(events)
                if event.kind == "cf"
                and event.frame.role == bad.role
                and event.ts < bad.ts
            ),
            None,
        )
        if previous is not None:
            evidence = [
                FrameEvidence(
                    frame_ref=previous.frame_ref,
                    ts=previous.ts_seconds,
                    line_no=previous.line_no,
                    can_id=previous.can_id,
                    role=previous.role,
                    data=previous.data,
                    summary="previous CF before sequence gap",
                ),
                *evidence,
            ]
    return build_finding(
        ctx=ctx,
        finding_id="ISO-TP-003",
        layer="ISO-TP",
        category="sn_gap",
        deviation_ts=issue.ts,
        detected_ts=issue.ts,
        observed=issue.observed,
        expected=issue.expected,
        suspected_side=sender_side(bad.role if bad is not None else None),
        base_confidence="high",
        detail={"transport_issue": issue.kind},
        evidence=evidence,
        session=session_at(ctx.sessions, issue.ts),
        window_covered=True,
    )


def missing_fc_after_block(issue: TransportIssue, ctx: RuleContext):
    window_role = next(
        (
            item.expected_role
            for item in issue.evidence
            if getattr(item, "type", None) == "absence_window"
        ),
        None,
    )
    # The absence window's expected role is the receiver's flow-control role.
    side = sender_side(window_role)
    if side != "unknown":
        side = "ecu" if side == "tester" else "tester"
    deviation_ts = _anchor_ts(issue)
    source = ctx.timing.isotp_fc.source
    return build_finding(
        ctx=ctx,
        finding_id="ISO-TP-004",
        layer="ISO-TP",
        category="missing_fc_after_block",
        deviation_ts=deviation_ts,
        detected_ts=issue.ts,
        observed=issue.observed,
        expected=issue.expected,
        suspected_side=side,
        base_confidence="high",
        detail={
            "timeout_ms": ctx.timing.isotp_fc.value_ms,
            "timing_source": source,
            "anchor_ts": deviation_ts,
            "deadline_ts": issue.ts,
        },
        evidence=list(issue.evidence),
        session=session_at(ctx.sessions, deviation_ts),
        timing_source=source,
        window_covered=issue_window_covered(issue),
    )


def stmin_violation(issue: TransportIssue, ctx: RuleContext):
    frame = _first_frame(issue)
    return build_finding(
        ctx=ctx,
        finding_id="ISO-TP-005",
        layer="ISO-TP",
        category="stmin_violation",
        deviation_ts=issue.ts,
        detected_ts=issue.ts,
        observed=issue.observed,
        expected=issue.expected,
        suspected_side=sender_side(frame.role if frame is not None else None),
        base_confidence="low",
        detail={"transport_issue": issue.kind},
        evidence=list(issue.evidence),
        session=session_at(ctx.sessions, issue.ts),
    )


__all__ = [
    "cf_after_cts_missing",
    "missing_fc_after_block",
    "missing_fc_after_ff",
    "sn_gap",
    "stmin_violation",
]
