from __future__ import annotations

"""ISO-TP eventization for the supported v1 transport profile.

The eventizer deliberately stays close to the record layer.  It does not
infer CAN FD from DLC and it does not put flow-control frames into a sender's
PDU.  That separation is what lets the validator reason over both directions
of a conversation later.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from ..models import (
    AddressedFrame,
    FrameEvidence,
    IsoTpConversation,
    IsoTpEvent,
    TraceWindow,
    TransportIssue,
)


@dataclass
class EventizationResult:
    """Events and diagnostics produced from addressed frames."""

    events: list[IsoTpEvent]
    issues: list[TransportIssue]
    input_stats: dict[str, Any]

    def __iter__(self):
        yield self.events
        yield self.issues

    def __len__(self) -> int:
        return len(self.events)

    def __getitem__(self, index: int) -> IsoTpEvent:
        return self.events[index]


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


def _unsupported_issue(
    frame: AddressedFrame,
    kind: str,
    observed: str,
    expected: str,
) -> TransportIssue:
    return TransportIssue(
        kind=kind,
        ts=frame.ts_seconds,
        severity="warning",
        observed=observed,
        expected=expected,
        evidence=[_frame_evidence(frame, observed)],
    )


def _explicit_addressing_mode(frame: AddressedFrame) -> str | None:
    metadata = frame.source_ts_metadata or {}
    for key in ("addressing_mode", "isotp_addressing_mode"):
        value = metadata.get(key)
        if isinstance(value, str) and value.lower() in {"normal", "extended", "mixed"}:
            return value.lower()
    for key in ("extended_addressing", "is_extended_addressing", "isotp_extended"):
        if metadata.get(key) is True:
            return "extended"
    for key in ("mixed_addressing", "is_mixed_addressing", "isotp_mixed"):
        if metadata.get(key) is True:
            return "mixed"
    return None


def _looks_like_unsupported_addressing(frame: AddressedFrame) -> str | None:
    """Return a conservative suspicion for an address byte before the PCI.

    In auto mode this is only a warning.  A normal-addressed frame whose first
    byte is an unknown PCI is handled as unsupported PCI instead.
    """

    if len(frame.data) < 2:
        return None
    first, second = frame.data[0], frame.data[1]
    if first & 0xF0 in {0x00, 0x10, 0x20, 0x30}:
        return None
    if second & 0xF0 in {0x00, 0x10, 0x20, 0x30}:
        return "extended"
    return None


def decode_event(
    frame: AddressedFrame,
    *,
    addressing_mode: str = "auto",
) -> tuple[IsoTpEvent | None, TransportIssue | None]:
    """Decode one normal-addressed CAN frame into an ISO-TP event.

    ``None`` is returned for frames that are unsupported or not usable as
    transport data.  Their reason is returned separately so callers can count
    it without confusing it with a valid ISO-TP event.
    """

    if frame.role not in {"tester->ecu", "ecu->tester"} or frame.pair_key is None:
        return None, None
    if frame.is_fd:
        return None, _unsupported_issue(
            frame,
            "unsupported_can_fd",
            "record is CAN FD (is_fd=True)",
            "Classical CAN ISO-TP only",
        )
    if frame.is_remote_frame or frame.is_error_frame or not frame.data:
        return None, _unsupported_issue(
            frame,
            "unsupported_pci",
            "remote/error/empty record cannot carry ISO-TP PCI",
            "data frame with PCI byte",
        )

    explicit_mode = _explicit_addressing_mode(frame)
    requested_mode = addressing_mode.lower()
    if requested_mode not in {"auto", "normal", "extended", "mixed"}:
        raise ValueError(f"unsupported addressing_mode: {addressing_mode}")
    if requested_mode in {"extended", "mixed"} or explicit_mode in {"extended", "mixed"}:
        mode = requested_mode if requested_mode in {"extended", "mixed"} else explicit_mode
        return None, _unsupported_issue(
            frame,
            "unsupported_addressing_mode",
            f"addressing_mode={mode}",
            "addressing_mode=normal",
        )
    if requested_mode == "auto" and explicit_mode is None:
        suspected = _looks_like_unsupported_addressing(frame)
        if suspected is not None:
            return None, _unsupported_issue(
                frame,
                "possible_unsupported_addressing_mode",
                f"possible {suspected} addressing: first byte is not PCI",
                "normal addressing with PCI at byte 0",
            )

    pci_raw = frame.data[0]
    pci_type = pci_raw >> 4
    if pci_type == 0x0:
        payload_len = pci_raw & 0x0F
        if not 1 <= payload_len <= 7 or len(frame.data) < 1 + payload_len:
            return None, _unsupported_issue(
                frame,
                "unsupported_pci",
                f"invalid SF length={payload_len} dlc={len(frame.data)}",
                "Classical CAN SF payload length 1..7",
            )
        return IsoTpEvent(
            kind="sf",
            ts=frame.ts_seconds,
            frame=frame,
            pci_raw=pci_raw,
            payload_len=payload_len,
            total_len=payload_len,
            sn=None,
            fs=None,
            bs=None,
            stmin_raw=None,
        ), None

    if pci_type == 0x1:
        if len(frame.data) < 2:
            return None, _unsupported_issue(
                frame,
                "unsupported_pci",
                "FF requires two PCI bytes",
                "FF with 12-bit total length",
            )
        total_len = ((pci_raw & 0x0F) << 8) | frame.data[1]
        if not 8 <= total_len <= 0xFFF:
            return None, _unsupported_issue(
                frame,
                "unsupported_pci",
                f"invalid FF total length={total_len}",
                "FF total length 8..4095",
            )
        return IsoTpEvent(
            kind="ff",
            ts=frame.ts_seconds,
            frame=frame,
            pci_raw=pci_raw,
            payload_len=max(len(frame.data) - 2, 0),
            total_len=total_len,
            sn=None,
            fs=None,
            bs=None,
            stmin_raw=None,
        ), None

    if pci_type == 0x2:
        return IsoTpEvent(
            kind="cf",
            ts=frame.ts_seconds,
            frame=frame,
            pci_raw=pci_raw,
            payload_len=max(len(frame.data) - 1, 0),
            total_len=None,
            sn=pci_raw & 0x0F,
            fs=None,
            bs=None,
            stmin_raw=None,
        ), None

    if pci_type == 0x3:
        if len(frame.data) < 3:
            return None, _unsupported_issue(
                frame,
                "unsupported_pci",
                "FC requires FS, BS, and STmin bytes",
                "FC with three PCI/control bytes",
            )
        return IsoTpEvent(
            kind="fc",
            ts=frame.ts_seconds,
            frame=frame,
            pci_raw=pci_raw,
            payload_len=None,
            total_len=None,
            sn=None,
            fs=pci_raw & 0x0F,
            bs=frame.data[1],
            stmin_raw=frame.data[2],
        ), None

    return None, _unsupported_issue(
        frame,
        "unsupported_pci",
        f"unknown N_PCI type=0x{pci_type:X}",
        "N_PCI type 0, 1, 2, or 3",
    )


def eventize_frames(
    frames: Iterable[AddressedFrame],
    *,
    addressing_mode: str = "auto",
) -> EventizationResult:
    """Decode addressed frames, preserving event order and diagnostics."""

    events: list[IsoTpEvent] = []
    issues: list[TransportIssue] = []
    skipped_roles = 0
    for frame in sorted(frames, key=lambda item: item.ts_seconds):
        if frame.role not in {"tester->ecu", "ecu->tester"} or frame.pair_key is None:
            skipped_roles += 1
            continue
        event, issue = decode_event(frame, addressing_mode=addressing_mode)
        if event is not None:
            events.append(event)
        if issue is not None:
            issues.append(issue)

    counts: dict[str, int] = defaultdict(int)
    for issue in issues:
        counts[issue.kind] += 1
    stats: dict[str, Any] = {
        "frame_count": len(events) + len(issues) + skipped_roles,
        "event_count": len(events),
        "skipped_role_count": skipped_roles,
        "unsupported_count": len(issues),
        "unsupported_counts": dict(counts),
    }
    for kind, count in counts.items():
        stats[f"{kind}_count"] = count
    return EventizationResult(events=events, issues=issues, input_stats=stats)


def events_from_frames(
    frames: Iterable[AddressedFrame],
    *,
    addressing_mode: str = "auto",
) -> list[IsoTpEvent]:
    """Convenience API returning only valid ISO-TP events."""

    return eventize_frames(frames, addressing_mode=addressing_mode).events


def decode_isotp_event(
    frame: AddressedFrame,
    *,
    addressing_mode: str = "auto",
) -> IsoTpEvent | None:
    """Compatibility convenience wrapper for callers needing one event."""

    event, _ = decode_event(frame, addressing_mode=addressing_mode)
    return event


def build_conversations(
    frames: Iterable[AddressedFrame],
    *,
    addressing_mode: str = "auto",
    trace_window: TraceWindow | None = None,
) -> list[IsoTpConversation]:
    """Group addressed frames into channel-isolated conversations and PDUs."""

    from .reconstructor import reconstruct_pdus

    grouped: dict[str, list[AddressedFrame]] = defaultdict(list)
    for frame in frames:
        if frame.pair_key is not None:
            grouped[frame.pair_key].append(frame)

    conversations: list[IsoTpConversation] = []
    for pair_key, pair_frames in grouped.items():
        result = eventize_frames(pair_frames, addressing_mode=addressing_mode)
        tester_events = [event for event in result.events if event.frame.role == "tester->ecu"]
        ecu_events = [event for event in result.events if event.frame.role == "ecu->tester"]
        pair_frames.sort(key=lambda frame: frame.ts_seconds)
        window = trace_window or TraceWindow(
            start_ts=pair_frames[0].ts_seconds,
            end_ts=pair_frames[-1].ts_seconds,
            coverage_ok=True,
        )
        pdus = reconstruct_pdus(
            tester_events,
            pair_key=pair_key,
            direction="tester->ecu",
        )
        pdus.extend(
            reconstruct_pdus(
                ecu_events,
                pair_key=pair_key,
                direction="ecu->tester",
            )
        )
        conversations.append(
            IsoTpConversation(
                pair_key=pair_key,
                tester_to_ecu_events=tester_events,
                ecu_to_tester_events=ecu_events,
                pdus=sorted(pdus, key=lambda pdu: pdu.ts_start),
                trace_window=window,
            )
        )
    return conversations


def build_conversation(
    frames: Iterable[AddressedFrame],
    *,
    addressing_mode: str = "auto",
    trace_window: TraceWindow | None = None,
) -> IsoTpConversation:
    conversations = build_conversations(
        frames,
        addressing_mode=addressing_mode,
        trace_window=trace_window,
    )
    if len(conversations) != 1:
        raise ValueError(f"expected exactly one conversation, got {len(conversations)}")
    return conversations[0]


eventize = eventize_frames
frames_to_events = events_from_frames


__all__ = [
    "EventizationResult",
    "build_conversation",
    "build_conversations",
    "decode_event",
    "decode_isotp_event",
    "eventize",
    "eventize_frames",
    "events_from_frames",
    "frames_to_events",
]
