from __future__ import annotations

import pytest

from flashreport_core.api import analyze_trace, default_config, load_trace
from flashreport_core.models import (
    AddressedFrame,
    FrameAnnotation,
    IsoTpConversation,
    IsoTpPdu,
    RawFrame,
    TraceBundle,
    TraceQuality,
    TraceWindow,
)
from flashreport_core.isotp.events import decode_event
from flashreport_core.isotp.reconstructor import reconstruct_pdus


PAIR_KEY = "1:18DA10F1<->18DAF110"


def _frame(data: bytes, ts: float, line: int, direction: str) -> AddressedFrame:
    raw = RawFrame(
        ts_seconds=ts,
        ts_display=f"{ts:.6f}",
        source_ts_metadata={},
        can_id=0x18DA10F1 if direction == "tester->ecu" else 0x18DAF110,
        is_extended=True,
        channel=1,
        is_fd=False,
        dlc=len(data),
        data=data,
        source="synthetic",
        line_no=line,
    )
    return AddressedFrame(**raw.__dict__, role=direction, pair_key=PAIR_KEY)


def _event(data: bytes, ts: float, line: int, direction: str):
    event, issue = decode_event(_frame(data, ts, line, direction))
    assert issue is None
    assert event is not None
    return event


def _conversation(tester_events, ecu_events, end_ts: float) -> tuple[IsoTpConversation, list[RawFrame]]:
    frames = [event.frame for event in tester_events + ecu_events]
    pdus = reconstruct_pdus(tester_events, pair_key=PAIR_KEY, direction="tester->ecu")
    pdus.extend(reconstruct_pdus(ecu_events, pair_key=PAIR_KEY, direction="ecu->tester"))
    conversation = IsoTpConversation(
        pair_key=PAIR_KEY,
        tester_to_ecu_events=sorted(tester_events, key=lambda event: event.ts),
        ecu_to_tester_events=sorted(ecu_events, key=lambda event: event.ts),
        pdus=sorted(pdus, key=lambda pdu: pdu.ts_start),
        trace_window=TraceWindow(start_ts=0.0, end_ts=end_ts, coverage_ok=True),
    )
    return conversation, frames


def _bundle(conversation: IsoTpConversation, frames: list[RawFrame], end_ts: float) -> TraceBundle:
    quality = TraceQuality(
        start_ts=0.0,
        end_ts=end_ts,
        has_capture_gap=False,
        dropped_frame_count=0,
        source_channels=[1],
        filter_state_known=True,
        completeness="verified",
    )
    annotations = {
        frame.frame_ref: FrameAnnotation(
            frame_ref=frame.frame_ref,
            direction=getattr(frame, "role", "other"),
            isotp_summary=None,
            uds_summary=None,
            summary=getattr(frame, "role", "other"),
        )
        for frame in frames
    }
    return TraceBundle(
        path="synthetic",
        frames=frames,
        conversations=[conversation],
        quality=quality,
        input_stats={},
        frame_annotations=annotations,
        conversation_summaries=[],
    )


def _direct_pdu(raw: bytes, ts: float, line: int, direction: str) -> IsoTpPdu:
    frame = _frame(raw, ts, line, direction)
    return IsoTpPdu(
        pair_key=PAIR_KEY,
        direction=direction,
        pci="single",
        payload=raw,
        ts_start=ts,
        ts_end=ts,
        frames=[frame],
    )


def _direct_bundle(pdus: list[IsoTpPdu], end_ts: float) -> TraceBundle:
    frames = [frame for pdu in pdus for frame in pdu.frames]
    conversation = IsoTpConversation(
        pair_key=PAIR_KEY,
        tester_to_ecu_events=[],
        ecu_to_tester_events=[],
        pdus=sorted(pdus, key=lambda pdu: pdu.ts_start),
        trace_window=TraceWindow(start_ts=0.0, end_ts=end_ts, coverage_ok=True),
    )
    return _bundle(conversation, frames, end_ts)


def _flash_bundle(record_length: int, end_ts: float = 5.0) -> TraceBundle:
    download_request = _direct_pdu(bytes.fromhex("3400440000"), 0.0, 1, "tester->ecu")
    download_response = _direct_pdu(bytes.fromhex("74200402"), 0.1, 2, "ecu->tester")
    transfer_raw = bytes([0x36, 0x01]) + b"A" * (record_length - 2)
    transfer_request = _direct_pdu(transfer_raw, 1.0, 3, "tester->ecu")
    transfer_response = _direct_pdu(bytes.fromhex("7601"), 1.1, 4, "ecu->tester")
    return _direct_bundle(
        [download_request, download_response, transfer_request, transfer_response], end_ts
    )


@pytest.mark.parametrize(
    ("record_length", "expected"),
    [(0x401, []), (0x402, []), (0x403, ["FLASH-001"])],
)
def test_flash_001_exact_length_boundaries(record_length: int, expected: list[str]) -> None:
    cfg = default_config()
    result = analyze_trace(_flash_bundle(record_length), cfg)
    assert [finding.finding_id for finding in result.findings] == expected
    if expected:
        assert result.findings[0].suspected_side == "tester"
        assert result.findings[0].confidence == "high"


def test_flash_001_wrong_bsc_is_a_tester_finding() -> None:
    pdus = [
        _direct_pdu(bytes.fromhex("3400440000"), 0.0, 1, "tester->ecu"),
        _direct_pdu(bytes.fromhex("74200402"), 0.01, 2, "ecu->tester"),
        _direct_pdu(bytes.fromhex("3602AA"), 1.0, 3, "tester->ecu"),
        _direct_pdu(bytes.fromhex("7F3673"), 1.01, 4, "ecu->tester"),
    ]
    result = analyze_trace(_direct_bundle(pdus, 2.0), default_config())
    finding = next(finding for finding in result.findings if finding.finding_id == "FLASH-001")
    assert finding.suspected_side == "tester"
    assert finding.confidence == "high"
    assert "bsc_error" in finding.detail["violations"]


def test_pending_then_final_response_is_not_a_finding() -> None:
    pdus = [
        _direct_pdu(bytes.fromhex("3601AA"), 1.0, 1, "tester->ecu"),
        _direct_pdu(bytes.fromhex("7F3678"), 1.1, 2, "ecu->tester"),
        _direct_pdu(bytes.fromhex("7601"), 1.2, 3, "ecu->tester"),
    ]
    result = analyze_trace(_direct_bundle(pdus, 2.0), default_config())
    assert result.findings == []


def test_pending_timeout_uses_default_assumption_and_is_medium() -> None:
    pdus = [
        _direct_pdu(bytes.fromhex("3601AA"), 1.0, 1, "tester->ecu"),
        _direct_pdu(bytes.fromhex("7F3678"), 1.1, 2, "ecu->tester"),
    ]
    result = analyze_trace(_direct_bundle(pdus, 6.2), default_config())
    assert [finding.finding_id for finding in result.findings] == ["UDS-001"]
    finding = result.findings[0]
    assert finding.confidence == "medium"
    assert finding.detail["timing_source"] == "default_assumption"
    assert finding.detail["timeout_ms"] == 5000


def test_observed_server_timing_allows_high_confidence_uds_timeout() -> None:
    pdus = [
        _direct_pdu(bytes.fromhex("1002"), 0.0, 1, "tester->ecu"),
        _direct_pdu(bytes.fromhex("5002003201F4"), 0.1, 2, "ecu->tester"),
        _direct_pdu(bytes.fromhex("3101"), 1.0, 3, "tester->ecu"),
        _direct_pdu(bytes.fromhex("7F3178"), 1.1, 4, "ecu->tester"),
    ]
    result = analyze_trace(_direct_bundle(pdus, 6.2), default_config())
    finding = next(finding for finding in result.findings if finding.finding_id == "UDS-001")
    assert finding.confidence == "high"
    assert finding.detail["timing_source"] == "observed_server"
    assert finding.detail["timeout_ms"] == 5000


def test_tester_finding_is_first_and_supersedes_later_ecu_timeout() -> None:
    download_request = _direct_pdu(bytes.fromhex("3400440000"), 0.0, 1, "tester->ecu")
    download_response = _direct_pdu(bytes.fromhex("74200402"), 0.1, 2, "ecu->tester")
    oversized = _direct_pdu(bytes([0x36, 1]) + b"B" * 0x401, 1.0, 3, "tester->ecu")
    later_request = _direct_pdu(bytes.fromhex("3101"), 2.0, 4, "tester->ecu")
    result = analyze_trace(
        _direct_bundle([download_request, download_response, oversized, later_request], 8.0),
        default_config(),
    )
    flash = next(finding for finding in result.findings if finding.finding_id == "FLASH-001")
    uds = next(finding for finding in result.findings if finding.finding_id == "UDS-001")
    assert result.first_deviation is flash
    assert uds.superseded_by == "FLASH-001"


def test_iso_tp_004_and_003_and_005_are_attributed() -> None:
    tester = [
        _event(bytes.fromhex("1020313233343536"), 1.0, 1, "tester->ecu"),
        _event(bytes.fromhex("213738393A3B3C3D"), 1.01, 3, "tester->ecu"),
        _event(bytes.fromhex("23414243444546"), 1.011, 4, "tester->ecu"),
    ]
    ecu = [_event(bytes.fromhex("300005"), 1.001, 2, "ecu->tester")]
    conversation, frames = _conversation(tester, ecu, 2.0)
    result = analyze_trace(_bundle(conversation, frames, 2.0), default_config())
    ids = [finding.finding_id for finding in result.findings]
    assert "ISO-TP-003" in ids
    assert "ISO-TP-005" in ids
    sn = next(finding for finding in result.findings if finding.finding_id == "ISO-TP-003")
    assert [e.type for e in sn.evidence] == ["frame", "frame"]

    block_tester = [
        _event(bytes.fromhex("1020313233343536"), 1.0, 11, "tester->ecu"),
        _event(bytes.fromhex("213738393A3B3C3D"), 1.01, 13, "tester->ecu"),
    ]
    block_ecu = [_event(bytes.fromhex("300105"), 1.001, 12, "ecu->tester")]
    block_conversation, block_frames = _conversation(block_tester, block_ecu, 2.0)
    block_result = analyze_trace(
        _bundle(block_conversation, block_frames, 2.0), default_config()
    )
    assert "ISO-TP-004" in [finding.finding_id for finding in block_result.findings]
