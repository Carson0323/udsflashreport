from __future__ import annotations

from flashreport_core.uds.decoder import (
    decode_uds,
    extract_server_timing,
    parse_max_block_length,
)


def test_request_and_positive_response_service_mapping() -> None:
    request = decode_uds(bytes.fromhex("1002"))
    response = decode_uds(bytes.fromhex("5002003201F4"))
    assert request.sid == 0x10
    assert request.service_name == "DiagnosticSessionControl"
    assert request.subfunction == 0x02
    assert request.is_positive is None
    assert response.sid == 0x50
    assert response.service_name == "DiagnosticSessionControl"
    assert response.subfunction == 0x02
    assert response.is_positive is True


def test_negative_response_and_nrc_translation() -> None:
    message = decode_uds(bytes.fromhex("7F3673"))
    assert message.sid == 0x7F
    assert message.service_name == "TransferData"
    assert message.is_positive is False
    assert message.nrc == 0x73
    assert message.nrc_text == "wrongBlockSequenceCounter"
    assert not message.pending


def test_pending_is_non_final_response() -> None:
    message = decode_uds(bytes.fromhex("7F1078"))
    assert message.pending
    assert message.nrc_text == "responsePending"


def test_transfer_data_block_sequence_is_decoded_for_request_and_response() -> None:
    request = decode_uds(bytes.fromhex("3617AABB"))
    response = decode_uds(bytes.fromhex("7617"))
    assert request.service_name == "TransferData"
    assert request.block_seq == 0x17
    assert response.block_seq == 0x17


def test_request_download_length_format_identifier() -> None:
    assert parse_max_block_length(bytes.fromhex("74200402")) == 0x402
    assert decode_uds(bytes.fromhex("74200402")).max_block_length == 0x402


def test_malformed_request_download_is_preserved_but_not_used_as_maximum() -> None:
    message = decode_uds(bytes.fromhex("74400200"))
    assert message.raw == bytes.fromhex("74400200")
    assert message.max_block_length is None
    assert parse_max_block_length(message) is None


def test_server_timing_uses_p2_ms_and_p2_star_ten_ms_units() -> None:
    timing = extract_server_timing(bytes.fromhex("5002003201F4"))
    assert timing is not None
    assert timing.p2_ms == 50
    assert timing.p2_star_ms == 5000
    assert extract_server_timing(bytes.fromhex("5002")) is None


def test_did_and_unknown_message_are_safe() -> None:
    did = decode_uds(bytes.fromhex("22F190"))
    unknown = decode_uds(bytes.fromhex("99AA"))
    empty = decode_uds(b"")
    assert did.did == 0xF190
    assert unknown.service_name is None and unknown.is_positive is None
    assert empty.sid is None and empty.raw == b""
