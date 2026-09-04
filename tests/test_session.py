from __future__ import annotations

from flashreport_core.models import IsoTpPdu, UdsTransaction
from flashreport_core.session.diagnostic import reconstruct_sessions
from flashreport_core.session.flash import reconstruct_flash_session
from flashreport_core.uds.decoder import decode_uds


def tx(request: str, response: str | None, ts: float, response_ts: float | None = None) -> UdsTransaction:
    req = decode_uds(bytes.fromhex(request))
    final = decode_uds(bytes.fromhex(response)) if response is not None else None
    pdu_req = IsoTpPdu(
        pair_key="pair",
        direction="tester->ecu",
        pci="single",
        payload=req.raw,
        ts_start=ts,
        ts_end=ts,
        frames=[],
    )
    pdu_resp = None
    if final is not None:
        pdu_resp = IsoTpPdu(
            pair_key="pair",
            direction="ecu->tester",
            pci="single",
            payload=final.raw,
            ts_start=response_ts if response_ts is not None else ts,
            ts_end=response_ts if response_ts is not None else ts,
            frames=[],
        )
    return UdsTransaction(
        request=req,
        pending_events=[],
        final_response=final,
        pdu_req=pdu_req,
        pdu_resp=pdu_resp,
    )


def test_diagnostic_session_switches_to_programming_and_extended() -> None:
    sessions = reconstruct_sessions(
        [
            tx("1002", "5002003201F4", 1.0, 1.1),
            tx("1003", "5003003201F4", 2.0, 2.1),
        ]
    )
    assert [session.session_type for session in sessions] == ["default", "programming", "extended"]
    assert sessions[1].start_ts == 1.1


def test_ecu_reset_returns_to_default_session() -> None:
    sessions = reconstruct_sessions(
        [tx("1002", "5002", 1.0, 1.1), tx("1101", "5101", 2.0, 2.1)]
    )
    assert sessions[-1].session_type == "default"
    assert sessions[-1].reason == "ecu_reset"


def test_s3_gap_is_best_effort_default_session_boundary() -> None:
    sessions = reconstruct_sessions(
        [tx("1002", "5002", 1.0, 1.1), tx("22F190", "62F190", 7.0, 7.1)],
        s3_timeout_ms=5000,
    )
    assert sessions[-1].session_type == "default"
    assert sessions[-1].reason == "s3_timeout"


def test_flash_session_records_max_block_length_and_expected_bsc() -> None:
    exact = "36" + "01" + "AA" * 1024
    oversize = "36" + "02" + "BB" * 1025
    session = reconstruct_flash_session(
        [
            tx("3400440000", "74200402", 1.0, 1.1),
            tx(exact, "7601", 2.0, 2.1),
            tx(oversize, "7602", 3.0, 3.1),
            tx("37", "77", 4.0, 4.1),
        ]
    )
    assert session is not None
    assert session.max_block_length == 0x402
    assert session.blocks[0].request_length == 0x402
    assert session.blocks[1].request_length == 0x403
    assert len(session.oversize_blocks) == 1
    assert session.expected_bsc == 3
    assert session.complete


def test_flash_session_records_wrong_block_sequence_counter() -> None:
    session = reconstruct_flash_session([tx("3400440000", "74200402", 1.0, 1.1), tx("3603AA", "7603", 2.0, 2.1)])
    assert session is not None
    assert len(session.bsc_errors) == 1
    assert session.bsc_errors[0].expected_block_seq == 1
