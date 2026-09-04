from __future__ import annotations

"""Shared context and evidence helpers for deterministic rule evaluators."""

from dataclasses import dataclass, field
from typing import Any

from ..models import (
    AddressedFrame,
    Evidence,
    Finding,
    FrameEvidence,
    IsoTpConversation,
    IsoTpPdu,
    ResolvedTimingConfig,
    TraceQuality,
    TransportIssue,
    UdsTransaction,
    WindowEvidence,
)
from ..session.flash import FlashBlock, FlashSession
from ..uds.pending import PendingIssue


@dataclass
class RuleContext:
    """All evidence available to one evaluator invocation."""

    conversation: IsoTpConversation | None
    quality: TraceQuality
    trace_end_ts: float
    timing: ResolvedTimingConfig
    issue: TransportIssue | PendingIssue | None = None
    transactions: list[UdsTransaction] = field(default_factory=list)
    sessions: list[Any] = field(default_factory=list)
    transaction: UdsTransaction | None = None
    pending_timestamps: list[float] = field(default_factory=list)
    flash_session: FlashSession | None = None
    flash_block: FlashBlock | None = None
    ambiguous: bool = False
    session_name: str | None = None


def sender_side(role: str | None) -> str:
    if role == "tester->ecu":
        return "tester"
    if role == "ecu->tester":
        return "ecu"
    return "unknown"


def receiver_side(role: str | None) -> str:
    side = sender_side(role)
    return {"tester": "ecu", "ecu": "tester"}.get(side, "unknown")


def opposite_role(role: str | None) -> str:
    return {"tester->ecu": "ecu->tester", "ecu->tester": "tester->ecu"}.get(
        role, "unknown"
    )


def frame_evidence(frame: AddressedFrame, summary: str) -> FrameEvidence:
    return FrameEvidence(
        frame_ref=frame.frame_ref,
        ts=frame.ts_seconds,
        line_no=frame.line_no,
        can_id=frame.can_id,
        role=frame.role,
        data=frame.data,
        summary=summary,
    )


def pdu_evidence(pdu: IsoTpPdu | None, summary: str) -> list[FrameEvidence]:
    """Use the first and last physical frame of a PDU as navigable evidence."""

    if pdu is None or not pdu.frames:
        return []
    selected = [pdu.frames[0]]
    if pdu.frames[-1].frame_ref != pdu.frames[0].frame_ref:
        selected.append(pdu.frames[-1])
    return [frame_evidence(frame, summary) for frame in selected]


def session_at(sessions: list[Any], ts: float) -> str | None:
    matches = [session for session in sessions if session.start_ts <= ts <= session.end_ts]
    if matches:
        return matches[-1].session_type
    previous = [session for session in sessions if session.start_ts <= ts]
    return previous[-1].session_type if previous else None


def confidence(
    base: str,
    *,
    quality: TraceQuality,
    window_covered: bool = True,
    timing_source: str | None = None,
    ambiguous: bool = False,
) -> str:
    """Apply the frozen confidence caps without inventing certainty."""

    order = {"low": 0, "medium": 1, "high": 2}
    value = order.get(base, 0)
    if not window_covered or quality.completeness == "known_incomplete" or ambiguous:
        value = min(value, order["medium"])
    if timing_source == "default_assumption":
        value = min(value, order["medium"])
    return {0: "low", 1: "medium", 2: "high"}[value]


def build_finding(
    *,
    ctx: RuleContext,
    finding_id: str,
    layer: str,
    category: str,
    deviation_ts: float,
    detected_ts: float,
    observed: str,
    expected: str,
    suspected_side: str,
    base_confidence: str,
    detail: dict[str, Any],
    evidence: list[Evidence],
    service: str | None = None,
    session: str | None = None,
    timing_source: str | None = None,
    window_covered: bool = True,
) -> Finding:
    detail = dict(detail)
    if ctx.conversation is not None:
        detail.setdefault("pair_key", ctx.conversation.pair_key)
    return Finding(
        finding_id=finding_id,
        layer=layer,
        category=category,
        deviation_ts=deviation_ts,
        detected_ts=detected_ts,
        observed=observed,
        expected=expected,
        suspected_side=suspected_side,
        confidence=confidence(
            base_confidence,
            quality=ctx.quality,
            window_covered=window_covered,
            timing_source=timing_source,
            ambiguous=ctx.ambiguous,
        ),
        session=session if session is not None else ctx.session_name,
        service=service,
        detail=detail,
        evidence=evidence,
    )


def issue_window_covered(issue: TransportIssue | PendingIssue | None) -> bool:
    if not isinstance(issue, TransportIssue):
        return True
    windows = [item for item in issue.evidence if isinstance(item, WindowEvidence)]
    return all(window.trace_coverage_ok for window in windows) if windows else True


__all__ = [
    "RuleContext",
    "build_finding",
    "confidence",
    "frame_evidence",
    "issue_window_covered",
    "opposite_role",
    "pdu_evidence",
    "receiver_side",
    "sender_side",
    "session_at",
]
