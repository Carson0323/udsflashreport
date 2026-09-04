from __future__ import annotations

"""Bidirectional ISO-TP transport validation."""

from dataclasses import dataclass
from typing import Iterable

from ..models import (
    AddressedFrame,
    FrameEvidence,
    IsoTpConversation,
    IsoTpEvent,
    TraceQuality,
    TimeoutsConfig,
    TransportIssue,
    WindowEvidence,
)


@dataclass(frozen=True)
class _FlowControlState:
    event: IsoTpEvent
    bs: int
    stmin_raw: int
    stmin_seconds: float | None


def stmin_to_seconds(value: int) -> float | None:
    """Convert ISO-TP STmin, returning ``None`` for reserved values."""

    value = int(value)
    if 0x00 <= value <= 0x7F:
        return value / 1000.0
    if 0xF1 <= value <= 0xF9:
        return (value - 0xF0) / 10000.0
    return None


decode_stmin = stmin_to_seconds


def _frame_evidence(frame: AddressedFrame, summary: str) -> FrameEvidence:
    return FrameEvidence(
        frame_ref=frame.frame_ref,
        ts=frame.ts_seconds,
        line_no=frame.line_no,
        can_id=frame.can_id,
        role=frame.role,
        data=frame.data,
        summary=summary,
    )


def _coverage_ok(quality: TraceQuality, start: float, end: float) -> bool:
    if end < start:
        return False
    if start < quality.start_ts or end > quality.end_ts:
        return False
    if quality.has_capture_gap is True:
        return False
    return quality.completeness in {"verified", "assumed"}


def _window_end(quality: TraceQuality, deadline: float) -> float:
    if quality.end_ts >= quality.start_ts:
        return min(deadline, quality.end_ts)
    return deadline


def _absence(
    *,
    quality: TraceQuality,
    start: float,
    deadline: float,
    expected_role: str,
    expected_kind: str,
    summary: str,
) -> WindowEvidence:
    end = _window_end(quality, deadline)
    return WindowEvidence(
        ts_start=start,
        ts_end=end,
        expected_role=expected_role,
        expected_kind=expected_kind,
        expected_can_id=None,
        matched_frame_count=0,
        trace_coverage_ok=_coverage_ok(quality, start, deadline),
        summary=summary,
    )


def _issue(
    *,
    kind: str,
    ts: float,
    severity: str,
    observed: str,
    expected: str,
    evidence: list[FrameEvidence | WindowEvidence],
) -> TransportIssue:
    return TransportIssue(
        kind=kind,
        ts=ts,
        severity=severity,  # type: ignore[arg-type]
        observed=observed,
        expected=expected,
        evidence=evidence,
    )


def _opposite(direction: str) -> str:
    return "ecu->tester" if direction == "tester->ecu" else "tester->ecu"


def _next_event(
    events: Iterable[IsoTpEvent],
    *,
    after: float,
    kind: str,
    before: float | None = None,
) -> IsoTpEvent | None:
    for event in events:
        if event.kind != kind or event.ts <= after:
            continue
        if before is not None and event.ts >= before:
            return None
        return event
    return None


def _first_fc_before(
    opposite_events: list[IsoTpEvent],
    *,
    after: float,
    deadline: float,
) -> IsoTpEvent | None:
    return _next_event(opposite_events, after=after, kind="fc", before=deadline + 1e-12)


def _wait_for_terminal_fc(
    receiver_events: list[IsoTpEvent],
    first_wait: IsoTpEvent,
    *,
    timeout: float,
) -> tuple[IsoTpEvent | None, float]:
    """Follow repeated WAIT frames until CTS/OVFLW or the WAIT deadline."""

    wait_deadline = first_wait.ts + timeout
    current = first_wait
    while current.fs == 1:
        next_fc = _next_event(receiver_events, after=current.ts, kind="fc")
        if next_fc is None or next_fc.ts > wait_deadline:
            return None, wait_deadline
        current = next_fc
    return current, wait_deadline


def _data_segment(
    events: list[IsoTpEvent],
    ff_index: int,
) -> tuple[IsoTpEvent, list[IsoTpEvent]]:
    """Return FF and CFs until the next PDU start in that direction."""

    ff = events[ff_index]
    segment: list[IsoTpEvent] = []
    for event in events[ff_index + 1 :]:
        if event.kind in {"ff", "sf"}:
            break
        if event.kind == "cf":
            segment.append(event)
    return ff, segment


def _pdu_complete_after(
    ff: IsoTpEvent,
    cf_count: int,
    cf_events: list[IsoTpEvent],
) -> tuple[bool, int]:
    total = ff.total_len or 0
    payload_count = max(len(ff.frame.data) - 2, 0)
    for event in cf_events[:cf_count]:
        payload_count += max(len(event.frame.data) - 1, 0)
    return total > 0 and payload_count >= total, payload_count


def _control_state(event: IsoTpEvent) -> _FlowControlState:
    bs = event.bs or 0
    stmin_raw = event.stmin_raw or 0
    return _FlowControlState(
        event=event,
        bs=bs,
        stmin_raw=stmin_raw,
        stmin_seconds=stmin_to_seconds(stmin_raw),
    )


def _validate_sender_flow(
    *,
    direction: str,
    sender_events: list[IsoTpEvent],
    receiver_events: list[IsoTpEvent],
    timing: TimeoutsConfig,
    quality: TraceQuality,
) -> list[TransportIssue]:
    issues: list[TransportIssue] = []
    fc_timeout = timing.isotp_fc_ms / 1000.0
    cf_timeout = timing.isotp_cf_ms / 1000.0
    receiver_role = _opposite(direction)

    for ff_index, event in enumerate(sender_events):
        if event.kind != "ff":
            continue
        ff, cf_events = _data_segment(sender_events, ff_index)
        deadline = ff.ts + fc_timeout
        first_fc = _first_fc_before(receiver_events, after=ff.ts, deadline=deadline)
        if first_fc is None:
            issues.append(
                _issue(
                    kind="missing_fc_after_ff",
                    ts=deadline,
                    severity="error",
                    observed="FF was not followed by FC within the configured timeout",
                    expected=f"FC within {timing.isotp_fc_ms} ms",
                    evidence=[
                        _frame_evidence(ff.frame, f"FF total_len={ff.total_len}"),
                        _absence(
                            quality=quality,
                            start=ff.ts,
                            deadline=deadline,
                            expected_role=receiver_role,
                            expected_kind="FC",
                            summary="No FC observed after FF",
                        ),
                    ],
                )
            )
            # CFs without an observed FC remain reconstructable, but there is
            # no CTS timing state from which to validate their spacing.
            continue

        control = _control_state(first_fc)
        if control.stmin_seconds is None:
            issues.append(
                _issue(
                    kind="stmin_reserved",
                    ts=first_fc.ts,
                    severity="warning",
                    observed=f"STmin=0x{control.stmin_raw:02X}",
                    expected="STmin 0x00..0x7F or 0xF1..0xF9",
                    evidence=[_frame_evidence(first_fc.frame, "FC contains reserved STmin")],
                )
            )

        if control.event.fs == 2:
            issues.append(
                _issue(
                    kind="overflow",
                    ts=first_fc.ts,
                    severity="error",
                    observed="FC FS=OVFLW",
                    expected="FC FS=CTS",
                    evidence=[
                        _frame_evidence(ff.frame, "FF awaiting receiver flow control"),
                        _frame_evidence(first_fc.frame, "FC FS=OVFLW"),
                    ],
                )
            )
            continue

        cts = first_fc
        if control.event.fs == 1:
            cts, wait_deadline = _wait_for_terminal_fc(
                receiver_events,
                first_fc,
                timeout=fc_timeout,
            )
            if cts is None:
                issues.append(
                    _issue(
                        kind="wait_timeout",
                        ts=wait_deadline,
                        severity="warning",
                        observed="FC WAIT was not followed by CTS in time",
                        expected=f"FC CTS within {timing.isotp_fc_ms} ms after WAIT",
                        evidence=[
                            _frame_evidence(first_fc.frame, "FC FS=WAIT"),
                            _absence(
                                quality=quality,
                                start=first_fc.ts,
                                deadline=wait_deadline,
                                expected_role=receiver_role,
                                expected_kind="FC CTS",
                                summary="No timely CTS observed after WAIT",
                            ),
                        ],
                    )
                )
                continue
            if cts.fs == 2:
                issues.append(
                    _issue(
                        kind="overflow",
                        ts=cts.ts,
                        severity="error",
                        observed="FC FS=OVFLW after WAIT",
                        expected="FC FS=CTS",
                        evidence=[
                            _frame_evidence(first_fc.frame, "FC FS=WAIT"),
                            _frame_evidence(cts.frame, "FC FS=OVFLW"),
                        ],
                    )
                )
                continue
            control = _control_state(cts)
            if control.stmin_seconds is None:
                issues.append(
                    _issue(
                        kind="stmin_reserved",
                        ts=cts.ts,
                        severity="warning",
                        observed=f"STmin=0x{control.stmin_raw:02X}",
                        expected="STmin 0x00..0x7F or 0xF1..0xF9",
                        evidence=[_frame_evidence(cts.frame, "CTS contains reserved STmin")],
                    )
                )

        pre_cts = [cf for cf in cf_events if cf.ts < cts.ts]
        if pre_cts:
            early = pre_cts[0]
            issues.append(
                _issue(
                    kind="cf_before_fc",
                    ts=early.ts,
                    severity="error",
                    observed=f"CF SN={early.sn} sent before CTS",
                    expected="FC CTS before the first CF",
                    evidence=[
                        _frame_evidence(ff.frame, "FF starts multi-frame PDU"),
                        _frame_evidence(early.frame, "CF before CTS"),
                        _frame_evidence(cts.frame, "CTS arrived after CF"),
                    ],
                )
            )

        post_cts = [cf for cf in cf_events if cf.ts >= cts.ts]
        completed_before_cts, _ = _pdu_complete_after(ff, len(pre_cts), pre_cts)
        if not post_cts:
            if completed_before_cts:
                continue
            issues.append(
                _issue(
                    kind="cf_after_cts_missing",
                    ts=cts.ts + cf_timeout,
                    severity="error",
                    observed="CTS was not followed by a CF within the configured timeout",
                    expected=f"CF within {timing.isotp_cf_ms} ms after CTS",
                    evidence=[
                        _frame_evidence(cts.frame, "FC FS=CTS"),
                        _absence(
                            quality=quality,
                            start=cts.ts,
                            deadline=cts.ts + cf_timeout,
                            expected_role=direction,
                            expected_kind="CF",
                            summary="No CF observed after CTS",
                        ),
                    ],
                )
            )
            continue

        # ISO-TP starts a multi-frame sequence at SN=1 and wraps from 0xF to
        # 0x0. This is independent of the first byte's PCI type.
        expected_sn = 1
        previous_cf_ts = cts.ts
        block_count = 0
        control_state = control
        for index, cf in enumerate(post_cts):
            gap = cf.ts - previous_cf_ts
            if cf_timeout > 0 and gap > cf_timeout:
                kind = "cf_after_cts_missing" if index == 0 else "timeout_cf_gap"
                issues.append(
                    _issue(
                        kind=kind,
                        ts=previous_cf_ts + cf_timeout,
                        severity="error",
                        observed=f"CF gap={gap * 1000:.3f} ms",
                        expected=f"CF gap <= {timing.isotp_cf_ms} ms",
                        evidence=[
                            _frame_evidence(
                                (control_state.event if index == 0 else post_cts[index - 1]).frame,
                                "last transport control/data event",
                            ),
                            _frame_evidence(cf.frame, "late CF"),
                            _absence(
                                quality=quality,
                                start=previous_cf_ts,
                                deadline=previous_cf_ts + cf_timeout,
                                expected_role=direction,
                                expected_kind="CF",
                                summary="No timely CF observed in the interval",
                            ),
                        ],
                    )
                )

            if cf.sn != expected_sn:
                issues.append(
                    _issue(
                        kind="sn_gap",
                        ts=cf.ts,
                        severity="error",
                        observed=f"SN={cf.sn}",
                        expected=f"SN={expected_sn}",
                        evidence=[_frame_evidence(cf.frame, "unexpected CF sequence number")],
                    )
                )
            expected_sn = ((cf.sn if cf.sn is not None else expected_sn) + 1) & 0x0F

            if control_state.stmin_seconds is not None and index > 0:
                delta = cf.ts - post_cts[index - 1].ts
                if delta + 1e-12 < control_state.stmin_seconds:
                    issues.append(
                        _issue(
                            kind="stmin_violation",
                            ts=cf.ts,
                            severity="warning",
                            observed=f"CF interval={delta * 1000:.3f} ms",
                            expected=f"CF interval >= {control_state.stmin_seconds * 1000:.3f} ms",
                            evidence=[
                                _frame_evidence(post_cts[index - 1].frame, "previous CF"),
                                _frame_evidence(cf.frame, "CF violates STmin"),
                            ],
                        )
                    )

            block_count += 1
            complete, _ = _pdu_complete_after(ff, index + 1, post_cts)
            if control_state.bs > 0 and block_count >= control_state.bs and not complete:
                next_fc = _next_event(receiver_events, after=cf.ts, kind="fc")
                block_deadline = cf.ts + fc_timeout
                extra = [
                    candidate
                    for candidate in post_cts[index + 1 :]
                    if next_fc is None or candidate.ts < next_fc.ts
                ]
                if next_fc is None or next_fc.ts > block_deadline:
                    if extra:
                        issues.append(
                            _issue(
                                kind="bs_violation",
                                ts=extra[0].ts,
                                severity="error",
                                observed=f"CF count exceeded BS={control_state.bs} before next FC",
                                expected="sender waits for next FC at block boundary",
                                evidence=[
                                    _frame_evidence(cf.frame, "BS boundary"),
                                    _frame_evidence(extra[0].frame, "CF before next FC"),
                                ],
                            )
                        )
                    issues.append(
                        _issue(
                            kind="missing_fc_after_block",
                            ts=block_deadline,
                            severity="error",
                            observed=f"BS={control_state.bs} block ended without timely FC",
                            expected=f"next FC within {timing.isotp_fc_ms} ms",
                            evidence=[
                                _frame_evidence(cf.frame, "last CF in block"),
                                _absence(
                                    quality=quality,
                                    start=cf.ts,
                                    deadline=block_deadline,
                                    expected_role=receiver_role,
                                    expected_kind="FC",
                                    summary="No FC observed at BS boundary",
                                ),
                            ],
                        )
                    )
                    # The next CFs belong to the same invalid block. One
                    # boundary issue plus one evidence-backed BS violation is
                    # more useful than repeating the same timeout per CF.
                    break
                else:
                    if extra:
                        issues.append(
                            _issue(
                                kind="bs_violation",
                                ts=extra[0].ts,
                                severity="error",
                                observed=f"CF count exceeded BS={control_state.bs} before next FC",
                                expected="sender waits for next FC at block boundary",
                                evidence=[
                                    _frame_evidence(cf.frame, "BS boundary"),
                                    _frame_evidence(extra[0].frame, "CF before next FC"),
                                ],
                            )
                        )
                    if next_fc.fs == 2:
                        issues.append(
                            _issue(
                                kind="overflow",
                                ts=next_fc.ts,
                                severity="error",
                                observed="FC FS=OVFLW at block boundary",
                                expected="FC FS=CTS",
                                evidence=[_frame_evidence(next_fc.frame, "FC FS=OVFLW")],
                            )
                        )
                        break
                    if next_fc.fs == 1:
                        cts_after_wait, wait_deadline = _wait_for_terminal_fc(
                            receiver_events,
                            next_fc,
                            timeout=fc_timeout,
                        )
                        if cts_after_wait is None:
                            issues.append(
                                _issue(
                                    kind="wait_timeout",
                                    ts=wait_deadline,
                                    severity="warning",
                                    observed="FC WAIT at block boundary was not followed by CTS",
                                    expected=f"FC CTS within {timing.isotp_fc_ms} ms",
                                    evidence=[_frame_evidence(next_fc.frame, "FC FS=WAIT")],
                                )
                            )
                            break
                        next_fc = cts_after_wait
                    control_state = _control_state(next_fc)
                    if control_state.stmin_seconds is None:
                        issues.append(
                            _issue(
                                kind="stmin_reserved",
                                ts=next_fc.ts,
                                severity="warning",
                                observed=f"STmin=0x{control_state.stmin_raw:02X}",
                                expected="STmin 0x00..0x7F or 0xF1..0xF9",
                                evidence=[_frame_evidence(next_fc.frame, "FC contains reserved STmin")],
                            )
                        )
                    block_count = 0
            previous_cf_ts = cf.ts

    return issues


def validate_conversation(
    conv: IsoTpConversation,
    timing: TimeoutsConfig,
    quality: TraceQuality,
) -> list[TransportIssue]:
    """Validate one conversation using both directional event timelines."""

    tester_events = sorted(conv.tester_to_ecu_events, key=lambda event: event.ts)
    ecu_events = sorted(conv.ecu_to_tester_events, key=lambda event: event.ts)
    issues = _validate_sender_flow(
        direction="tester->ecu",
        sender_events=tester_events,
        receiver_events=ecu_events,
        timing=timing,
        quality=quality,
    )
    issues.extend(
        _validate_sender_flow(
            direction="ecu->tester",
            sender_events=ecu_events,
            receiver_events=tester_events,
            timing=timing,
            quality=quality,
        )
    )
    return sorted(issues, key=lambda issue: issue.ts)


validate = validate_conversation


__all__ = ["decode_stmin", "stmin_to_seconds", "validate", "validate_conversation"]
