from __future__ import annotations

"""Deterministic decoding for the UDS service subset frozen in the spec."""

from dataclasses import dataclass

from ..models import IsoTpPdu, UdsMessage
from .tables import (
    POSITIVE_SERVICE_NAMES,
    SERVICE_NAMES,
    SUBFUNCTION_SERVICES,
    base_service_sid,
    nrc_name,
    service_name,
)


@dataclass(frozen=True)
class ServerTiming:
    """Timing announced by a positive DiagnosticSessionControl response."""

    p2_ms: int
    p2_star_ms: int


def _payload(value: bytes | bytearray | IsoTpPdu | UdsMessage) -> bytes:
    if isinstance(value, IsoTpPdu):
        return bytes(value.payload or b"")
    if isinstance(value, UdsMessage):
        return value.raw
    return bytes(value)


def decode_uds(value: bytes | bytearray | IsoTpPdu) -> UdsMessage:
    """Decode one complete or partial UDS payload without raising on truncation."""

    raw = _payload(value)
    if not raw:
        return UdsMessage(
            sid=None,
            service_name=None,
            subfunction=None,
            did=None,
            block_seq=None,
            max_block_length=None,
            is_positive=None,
            nrc=None,
            nrc_text=None,
            raw=raw,
        )

    sid = raw[0]
    negative = sid == 0x7F
    positive = sid in POSITIVE_SERVICE_NAMES
    base_sid = base_service_sid(sid, raw)
    name = service_name(base_sid)
    subfunction: int | None = None
    did: int | None = None
    block_seq: int | None = None
    max_block_length: int | None = None
    nrc: int | None = None

    if negative:
        nrc = raw[2] if len(raw) >= 3 else None
    elif base_sid in SUBFUNCTION_SERVICES:
        if len(raw) >= 2:
            subfunction = raw[1] & 0x7F
    elif base_sid in {0x22, 0x2E}:
        if len(raw) >= 3:
            did = int.from_bytes(raw[1:3], "big")
    elif base_sid == 0x36:
        if len(raw) >= 2:
            block_seq = raw[1]
    elif sid == 0x74:
        max_block_length = parse_max_block_length(raw)

    return UdsMessage(
        sid=sid,
        service_name=name,
        subfunction=subfunction,
        did=did,
        block_seq=block_seq,
        max_block_length=max_block_length,
        is_positive=True if positive else False if negative else None,
        nrc=nrc,
        nrc_text=nrc_name(nrc),
        pending=nrc == 0x78,
        raw=raw,
    )


def parse_max_block_length(raw: bytes | bytearray | IsoTpPdu | UdsMessage) -> int | None:
    """Parse 0x74 using the response length-format identifier.

    The first response-data byte's high nibble is the number of bytes that
    encode maxNumberOfBlockLength.  Truncated/zero-width/over-wide forms are
    returned as ``None`` so attribution cannot silently use an uncertain
    field.  The caller can still display the original raw payload.
    """

    payload = _payload(raw)
    if len(payload) < 2 or payload[0] != 0x74:
        return None
    length_bytes = payload[1] >> 4
    if not 1 <= length_bytes <= 8 or len(payload) < 2 + length_bytes:
        return None
    return int.from_bytes(payload[2 : 2 + length_bytes], "big")


def extract_server_timing(raw: bytes | bytearray | IsoTpPdu | UdsMessage) -> ServerTiming | None:
    """Extract P2/P2* from a standard positive 0x50 response.

    P2 is encoded in milliseconds; P2* is encoded in 10 ms units.  A response
    with an unexpected length is preserved by the decoder but does not produce
    timing provenance.
    """

    if isinstance(raw, UdsMessage):
        payload = raw.raw
    else:
        payload = _payload(raw)
    if len(payload) != 6 or payload[0] != 0x50:
        return None
    return ServerTiming(
        p2_ms=int.from_bytes(payload[2:4], "big"),
        p2_star_ms=int.from_bytes(payload[4:6], "big") * 10,
    )


def decode_pdu(pdu: IsoTpPdu) -> UdsMessage:
    return decode_uds(pdu)


decode = decode_uds
decode_message = decode_uds
parse_uds = decode_uds
decode_uds_message = decode_uds


__all__ = [
    "ServerTiming",
    "decode",
    "decode_message",
    "decode_pdu",
    "decode_uds",
    "decode_uds_message",
    "extract_server_timing",
    "parse_max_block_length",
    "parse_uds",
]
