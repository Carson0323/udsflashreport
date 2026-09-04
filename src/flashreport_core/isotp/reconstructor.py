from __future__ import annotations

"""Direction-local ISO-TP PDU reconstruction.

Only FF/CF are needed to reconstruct a payload.  FC is intentionally ignored
here and is validated by :mod:`flashreport_core.isotp.validator` against the
opposite event stream.
"""

from typing import Iterable, Sequence

from ..models import (
    AddressedFrame,
    FrameEvidence,
    IsoTpEvent,
    IsoTpPdu,
    TimeoutsConfig,
    TransportIssue,
)
from .events import events_from_frames


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


def _issue(
    kind: str,
    event: IsoTpEvent,
    *,
    observed: str,
    expected: str,
    extra_evidence: list[FrameEvidence] | None = None,
) -> TransportIssue:
    evidence = [_frame_evidence(event.frame, observed)]
    if extra_evidence:
        evidence.extend(extra_evidence)
    return TransportIssue(
        kind=kind,
        ts=event.ts,
        severity="error",
        observed=observed,
        expected=expected,
        evidence=evidence,
    )


def _coerce_events(
    events: Iterable[IsoTpEvent | AddressedFrame],
) -> list[IsoTpEvent]:
    values = list(events)
    if not values:
        return []
    if all(isinstance(value, IsoTpEvent) for value in values):
        return sorted(values, key=lambda event: event.ts)
    if all(isinstance(value, AddressedFrame) for value in values):
        return events_from_frames(values)
    raise TypeError("events must contain only IsoTpEvent or AddressedFrame values")


def _new_pdu(
    event: IsoTpEvent,
    *,
    pair_key: str,
    direction: str,
    payload: bytes,
    frames: list[AddressedFrame],
    incomplete: bool = False,
    incomplete_reason: str | None = None,
    issues: list[TransportIssue] | None = None,
) -> IsoTpPdu:
    return IsoTpPdu(
        pair_key=pair_key,
        direction=direction,
        pci="multi",
        payload=payload,
        ts_start=frames[0].ts_seconds,
        ts_end=frames[-1].ts_seconds,
        frames=frames,
        incomplete=incomplete,
        incomplete_reason=incomplete_reason,
        issues=list(issues or []),
    )


def reconstruct_pdus(
    events: Sequence[IsoTpEvent | AddressedFrame] | Iterable[IsoTpEvent | AddressedFrame],
    *,
    pair_key: str | None = None,
    direction: str | None = None,
    timing: TimeoutsConfig | None = None,
) -> list[IsoTpPdu]:
    """Reconstruct single- and multi-frame PDUs from one direction.

    Missing FC is not an incomplete-PDU condition.  A complete FF/CF sequence
    therefore reconstructs successfully even when the opposite event stream
    contains no FC; the validator reports that transport defect separately.
    """

    decoded = _coerce_events(events)
    if not decoded:
        return []
    pair_key = pair_key or decoded[0].frame.pair_key
    direction = direction or decoded[0].frame.role
    if pair_key is None or direction is None:
        raise ValueError("pair_key and direction are required when events have no pair metadata")
    if timing is None:
        timing = TimeoutsConfig()
    timeout_s = timing.isotp_cf_ms / 1000.0

    pdus: list[IsoTpPdu] = []
    active: dict[str, object] | None = None

    def finish_active(
        *,
        incomplete: bool,
        reason: str | None = None,
        issue: TransportIssue | None = None,
    ) -> None:
        nonlocal active
        if active is None:
            return
        frames = active["frames"]
        issues = list(active["issues"])
        if issue is not None:
            issues.append(issue)
        pdu = _new_pdu(
            active["ff"],
            pair_key=pair_key,
            direction=direction,
            payload=bytes(active["payload"]),
            frames=frames,
            incomplete=incomplete,
            incomplete_reason=reason,
            issues=issues,
        )
        pdus.append(pdu)
        active = None

    for event in decoded:
        if event.kind == "sf":
            if active is not None:
                finish_active(incomplete=True, reason="new_pdu_before_completion")
            payload_len = event.payload_len or 0
            pdus.append(
                IsoTpPdu(
                    pair_key=pair_key,
                    direction=direction,
                    pci="single",
                    payload=event.frame.data[1 : 1 + payload_len],
                    ts_start=event.ts,
                    ts_end=event.ts,
                    frames=[event.frame],
                )
            )
            continue

        if event.kind == "ff":
            if active is not None:
                finish_active(incomplete=True, reason="new_ff_before_completion")
            active = {
                "ff": event,
                "total_len": event.total_len or 0,
                "payload": bytearray(event.frame.data[2:]),
                "frames": [event.frame],
                # ISO-TP starts a multi-frame sequence at SN=1 and wraps
                # from 0xF back to 0x0.
                "expected_sn": 1,
                "last_ts": event.ts,
                "issues": [],
            }
            if len(active["payload"]) >= active["total_len"]:
                active["payload"] = active["payload"][: active["total_len"]]
                finish_active(incomplete=False)
            continue

        if event.kind != "cf" or active is None:
            # FC belongs to the opposite direction.  An orphan CF is a
            # validator concern and cannot form a reliable PDU by itself.
            continue

        gap = event.ts - active["last_ts"]
        if timeout_s > 0 and gap > timeout_s:
            finish_active(
                incomplete=True,
                reason="timeout_cf_gap",
                issue=_issue(
                    "timeout_cf_gap",
                    event,
                    observed=f"CF gap={gap * 1000:.3f} ms",
                    expected=f"CF gap <= {timing.isotp_cf_ms} ms",
                ),
            )
            continue

        expected_sn = active["expected_sn"]
        if event.sn != expected_sn:
            finish_active(
                incomplete=True,
                reason="sn_gap",
                issue=_issue(
                    "sn_gap",
                    event,
                    observed=f"SN={event.sn}",
                    expected=f"SN={expected_sn}",
                ),
            )
            continue

        active["payload"].extend(event.frame.data[1:])
        active["frames"].append(event.frame)
        active["last_ts"] = event.ts
        active["expected_sn"] = (expected_sn + 1) & 0x0F
        if len(active["payload"]) >= active["total_len"]:
            active["payload"] = active["payload"][: active["total_len"]]
            finish_active(incomplete=False)

    if active is not None:
        finish_active(incomplete=True, reason="missing_cf")

    return sorted(pdus, key=lambda pdu: pdu.ts_start)


def reconstruct_direction(
    events: Sequence[IsoTpEvent | AddressedFrame] | Iterable[IsoTpEvent | AddressedFrame],
    *,
    pair_key: str | None = None,
    direction: str | None = None,
    timing: TimeoutsConfig | None = None,
) -> list[IsoTpPdu]:
    return reconstruct_pdus(
        events,
        pair_key=pair_key,
        direction=direction,
        timing=timing,
    )


reconstruct = reconstruct_pdus


__all__ = ["reconstruct", "reconstruct_direction", "reconstruct_pdus"]
