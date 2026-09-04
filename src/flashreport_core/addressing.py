from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import AddressedFrame, AddressingConfig, AppConfig, ManualPair, RawFrame
from .uds.tables import POSITIVE_SERVICE_NAMES, SERVICE_NAMES


FUNCTIONAL_REQUEST_ID = 0x18DB33F1
FUNCTIONAL_REQUEST_ID_11BIT = 0x7DF
NORMAL_FIXED_BASE = 0x18DA0000


def make_pair_key(channel: int | str | None, request_id: int, response_id: int) -> str:
    return f"{channel}:{request_id:08X}<->{response_id:08X}"


def _addressing_config(config: AddressingConfig | AppConfig) -> AddressingConfig:
    return config.addressing if isinstance(config, AppConfig) else config


def _parse_id(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return int(value.strip().lower().removeprefix("0x"), 16)


def _channel_matches(frame: RawFrame, pair: ManualPair) -> bool:
    return pair.channel is None or frame.channel == pair.channel


def _manual_match(frame: RawFrame, pair: ManualPair) -> tuple[str, str] | None:
    if not _channel_matches(frame, pair) or frame.is_extended != pair.is_extended_id:
        return None
    request_id = _parse_id(pair.request_id)
    response_id = _parse_id(pair.response_id)
    pair_key = make_pair_key(pair.channel if pair.channel is not None else frame.channel, request_id, response_id)
    if frame.can_id == request_id:
        return "tester->ecu", pair_key
    if frame.can_id == response_id:
        return "ecu->tester", pair_key
    return None


def _auto_29bit(frame: RawFrame, tester_sa: int) -> tuple[str, str] | None:
    if not frame.is_extended:
        return None
    can_id = frame.can_id
    request_match = (can_id & 0x1FFF00FF) == (NORMAL_FIXED_BASE | tester_sa)
    if request_match:
        ecu_sa = (can_id >> 8) & 0xFF
        request_id = NORMAL_FIXED_BASE | (ecu_sa << 8) | tester_sa
        response_id = NORMAL_FIXED_BASE | (tester_sa << 8) | ecu_sa
        return "tester->ecu", make_pair_key(frame.channel, request_id, response_id)

    response_match = (can_id & 0x1FFFFF00) == (NORMAL_FIXED_BASE | (tester_sa << 8))
    if response_match:
        ecu_sa = can_id & 0xFF
        request_id = NORMAL_FIXED_BASE | (ecu_sa << 8) | tester_sa
        response_id = NORMAL_FIXED_BASE | (tester_sa << 8) | ecu_sa
        return "ecu->tester", make_pair_key(frame.channel, request_id, response_id)
    return None


def _auto_11bit(frame: RawFrame) -> tuple[str, str] | None:
    if frame.is_extended:
        return None
    if 0x7E0 <= frame.can_id <= 0x7E7:
        request_id = frame.can_id
        response_id = request_id + 0x8
        return "tester->ecu", make_pair_key(frame.channel, request_id, response_id)
    if 0x7E8 <= frame.can_id <= 0x7EF:
        response_id = frame.can_id
        request_id = response_id - 0x8
        return "ecu->tester", make_pair_key(frame.channel, request_id, response_id)
    return None


def _normal_fixed_candidate(frame: RawFrame) -> tuple[int, int] | None:
    """Return the symmetric 29-bit pair without assuming tester SA=F1.

    The configured tester SA remains the primary, deterministic path.  This
    fallback is intentionally limited to normal-fixed diagnostic IDs so a BLF
    from another tester address can still be analyzed directly and reviewed
    by a human.
    """

    if not frame.is_extended or (frame.can_id & 0x1FFF0000) != NORMAL_FIXED_BASE:
        return None
    first = (frame.can_id >> 8) & 0xFF
    second = frame.can_id & 0xFF
    if first == second:
        return None
    request_id = NORMAL_FIXED_BASE | (first << 8) | second
    response_id = NORMAL_FIXED_BASE | (second << 8) | first
    return request_id, response_id


def _uds_sid_hint(frame: RawFrame) -> str | None:
    """Classify a first SF/FF UDS SID for dynamic-pair orientation."""

    if not frame.data:
        return None
    pci_type = frame.data[0] >> 4
    if pci_type == 0x0:
        payload_len = frame.data[0] & 0x0F
        if payload_len < 1 or len(frame.data) < 2:
            return None
        sid = frame.data[1]
    elif pci_type == 0x1 and len(frame.data) >= 3:
        sid = frame.data[2]
    else:
        return None
    if sid == 0x7F or sid in POSITIVE_SERVICE_NAMES:
        return "response"
    if sid in SERVICE_NAMES:
        return "request"
    return None


def _address_one(frame: RawFrame, config: AddressingConfig) -> tuple[str, str | None]:
    for pair in config.manual_pairs:
        match = _manual_match(frame, pair)
        if match is not None:
            return match

    if frame.is_extended and (
        frame.can_id == FUNCTIONAL_REQUEST_ID
        or (frame.can_id & 0x1FFFFF00) == (FUNCTIONAL_REQUEST_ID & 0x1FFFFF00)
    ):
        return "functional", None
    if not frame.is_extended and frame.can_id == FUNCTIONAL_REQUEST_ID_11BIT:
        return "functional", None

    if config.auto_detect and config.enable_29bit_normal_fixed:
        auto_29bit = _auto_29bit(frame, _parse_id(config.tester_sa))
        if auto_29bit is not None:
            return auto_29bit
    if config.auto_detect and config.enable_11bit_heuristic:
        auto_11bit = _auto_11bit(frame)
        if auto_11bit is not None:
            return auto_11bit
    return "other", None


def address_frames(
    frames: Iterable[RawFrame],
    config: AddressingConfig | AppConfig | None = None,
) -> list[AddressedFrame]:
    addressing = config or AddressingConfig()
    addressing = _addressing_config(addressing)
    source_frames = list(frames)
    addressed: list[AddressedFrame | None] = []
    dynamic_groups: dict[tuple[int | str | None, tuple[int, int]], list[tuple[int, RawFrame, tuple[int, int]]]] = defaultdict(list)
    for index, frame in enumerate(source_frames):
        role, pair_key = _address_one(frame, addressing)
        if role == "other":
            candidate = _normal_fixed_candidate(frame)
            if candidate is not None:
                dynamic_groups[
                    (frame.channel, tuple(sorted(candidate)))
                ].append((index, frame, candidate))
                addressed.append(None)
                continue
        addressed.append(AddressedFrame(**frame.__dict__, role=role, pair_key=pair_key))

    for items in dynamic_groups.values():
        request_id, response_id = items[0][2]
        hints = [_uds_sid_hint(frame) for _index, frame, _candidate in items]
        if not any(hints) and len({frame.can_id for _index, frame, _candidate in items}) < 2:
            for index, frame, _candidate in items:
                addressed[index] = AddressedFrame(
                    **frame.__dict__, role="other", pair_key=None
                )
            continue
        # First use a UDS request/response SID to orient the pair.  For CF/FC
        # records, reuse that orientation.  If the trace contains no hint,
        # retain the first observed ID as the provisional request side.
        for _index, frame, candidate in items:
            hint = _uds_sid_hint(frame)
            if hint == "request":
                request_id, response_id = frame.can_id, candidate[1] if frame.can_id == candidate[0] else candidate[0]
                break
            if hint == "response":
                response_id, request_id = frame.can_id, candidate[1] if frame.can_id == candidate[0] else candidate[0]
                break
        pair_key = make_pair_key(items[0][1].channel, request_id, response_id)
        for index, frame, _candidate in items:
            if frame.can_id == request_id:
                role = "tester->ecu"
            elif frame.can_id == response_id:
                role = "ecu->tester"
            else:
                role = "other"
                pair_key_for_frame = None
                addressed[index] = AddressedFrame(
                    **frame.__dict__, role=role, pair_key=pair_key_for_frame
                )
                continue
            addressed[index] = AddressedFrame(**frame.__dict__, role=role, pair_key=pair_key)

    return [item for item in addressed if item is not None]


def address_trace(
    frames: Iterable[RawFrame],
    config: AddressingConfig | AppConfig | None = None,
) -> list[AddressedFrame]:
    return address_frames(frames, config)


apply_addressing = address_frames
filter_frames = address_frames


def group_by_pair_key(frames: Iterable[AddressedFrame]) -> dict[str, list[AddressedFrame]]:
    grouped: dict[str, list[AddressedFrame]] = defaultdict(list)
    for frame in frames:
        if frame.pair_key is not None:
            grouped[frame.pair_key].append(frame)
    return dict(grouped)


__all__ = [
    "FUNCTIONAL_REQUEST_ID",
    "FUNCTIONAL_REQUEST_ID_11BIT",
    "NORMAL_FIXED_BASE",
    "address_frames",
    "address_trace",
    "apply_addressing",
    "filter_frames",
    "group_by_pair_key",
    "make_pair_key",
]
