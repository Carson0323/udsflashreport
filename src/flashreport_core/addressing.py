from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import AddressedFrame, AddressingConfig, AppConfig, ManualPair, RawFrame


FUNCTIONAL_REQUEST_ID = 0x18DB33F1
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


def _address_one(frame: RawFrame, config: AddressingConfig) -> tuple[str, str | None]:
    for pair in config.manual_pairs:
        match = _manual_match(frame, pair)
        if match is not None:
            return match

    if frame.is_extended and frame.can_id == FUNCTIONAL_REQUEST_ID:
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
    return [
        AddressedFrame(**frame.__dict__, role=role, pair_key=pair_key)
        for frame in frames
        for role, pair_key in [_address_one(frame, addressing)]
    ]


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
    "NORMAL_FIXED_BASE",
    "address_frames",
    "address_trace",
    "apply_addressing",
    "filter_frames",
    "group_by_pair_key",
    "make_pair_key",
]
