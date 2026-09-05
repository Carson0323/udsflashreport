from __future__ import annotations

import pytest

from flashreport_core.api import analyze_trace, default_config, load_trace
from flashreport_core.addressing import FUNCTIONAL_REQUEST_ID_11BIT, address_frames
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
from flashreport_core.uds.decoder import decode_uds


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


def test_missing_fc_uses_ff_as_deviation_and_deadline_as_detection_timestamp() -> None:
    ff = _event(bytes.fromhex("100922F190000000"), 1.0, 1, "tester->ecu")
    conversation, frames = _conversation([ff], [], 2.0)
    result = analyze_trace(_bundle(conversation, frames, 2.0), default_config())
    finding = next(item for item in result.findings if item.finding_id == "ISO-TP-001")
    assert finding.deviation_ts == 1.0
    assert finding.detected_ts == 2.0
    assert finding.evidence[0].frame_ref == "synthetic:1"


def test_final_ecu_negative_response_is_a_locatable_finding() -> None:
    pdus = [
        _direct_pdu(bytes.fromhex("3400440000"), 1.0, 1, "tester->ecu"),
        _direct_pdu(bytes.fromhex("7F3472"), 1.1, 2, "ecu->tester"),
    ]
    result = analyze_trace(_direct_bundle(pdus, 2.0), default_config())
    finding = next(finding for finding in result.findings if finding.finding_id == "UDS-002")
    assert finding.suspected_side == "ecu"
    assert finding.detail["nrc"] == 0x72
    assert [e.frame_ref for e in finding.evidence] == [
        pdus[0].frames[0].frame_ref,
        pdus[1].frames[0].frame_ref,
    ]


def test_decoder_and_workflow_keep_exact_did_data_and_compact_transfer_data() -> None:
    assert decode_uds(bytes.fromhex("2E1234AABB")).did == 0x1234
    assert decode_uds(bytes.fromhex("6E1234")).did == 0x1234
    valid_download = _direct_pdu(bytes.fromhex("3400440000000000000400"), 0.0, 1, "tester->ecu")
    valid_download_response = _direct_pdu(bytes.fromhex("74200402"), 0.1, 2, "ecu->tester")
    valid_transfer = _direct_pdu(bytes([0x36, 0x01]) + b"A" * 0x401, 1.0, 3, "tester->ecu")
    valid_transfer_response = _direct_pdu(bytes.fromhex("7601"), 1.1, 4, "ecu->tester")
    result = analyze_trace(
        _direct_bundle(
            [valid_download, valid_download_response, valid_transfer, valid_transfer_response],
            2.0,
        ),
        default_config(),
    )
    workflow = result.workflow_steps
    download = next(step for step in workflow if step["sid"] == 0x34)
    transfer = next(step for step in workflow if step["sid"] == 0x36)
    assert "start=0x0" in download["detail"]
    assert "length=0x400" in download["detail"]
    assert transfer["fields"]["transfer_data_length"] == 0x401
    assert transfer["fields"]["raw"].startswith("36 BSC=01 payload_bytes=")
    assert len(transfer["fields"]["raw"]) < 64


def test_standard_11bit_functional_address_is_explicit() -> None:
    raw = RawFrame(
        ts_seconds=1.0,
        ts_display="1.000000",
        source_ts_metadata={},
        can_id=FUNCTIONAL_REQUEST_ID_11BIT,
        is_extended=False,
        channel=1,
        is_fd=False,
        dlc=3,
        data=bytes.fromhex("021003"),
        source="synthetic",
        line_no=1,
    )
    addressed = address_frames([raw], default_config().addressing)
    assert addressed[0].role == "functional"
    assert addressed[0].pair_key is None


def test_workflow_describes_read_write_did_content() -> None:
    pdus = [
        _direct_pdu(bytes.fromhex("2E12343132"), 1.0, 1, "tester->ecu"),
        _direct_pdu(bytes.fromhex("6E1234"), 1.1, 2, "ecu->tester"),
        _direct_pdu(bytes.fromhex("221234"), 2.0, 3, "tester->ecu"),
        _direct_pdu(bytes.fromhex("6212344142"), 2.1, 4, "ecu->tester"),
    ]
    result = analyze_trace(_direct_bundle(pdus, 3.0), default_config())
    write_step = next(step for step in result.workflow_steps if step["sid"] == 0x2E)
    read_step = next(step for step in result.workflow_steps if step["sid"] == 0x22)
    assert "DID=0x1234" in write_step["detail"]
    assert "write_data=31 32" in write_step["detail"]
    assert "ASCII=12" in write_step["detail"]
    assert "DID=0x1234" in read_step["detail"]
    assert "read_data=41 42" in read_step["detail"]
    assert "ASCII=AB" in read_step["detail"]
    write_annotation = result.frame_annotations[pdus[0].frames[0].frame_ref]
    assert write_annotation.uds_details["did_bytes"] == "12 34"
    assert write_annotation.uds_details["write_data"] == "31 32"
    assert write_annotation.uds_details["write_ascii"] == "12"


def test_workflow_retains_functional_addressing_step() -> None:
    raw = RawFrame(
        ts_seconds=1.0,
        ts_display="1.000000",
        source_ts_metadata={},
        can_id=FUNCTIONAL_REQUEST_ID_11BIT,
        is_extended=False,
        channel=1,
        is_fd=False,
        dlc=3,
        data=bytes.fromhex("021003"),
        source="synthetic",
        line_no=1,
    )
    bundle = TraceBundle(
        path="synthetic",
        frames=[raw],
        conversations=[],
        quality=TraceQuality(
            start_ts=1.0,
            end_ts=1.0,
            has_capture_gap=False,
            dropped_frame_count=0,
            source_channels=[1],
            filter_state_known=True,
            completeness="verified",
        ),
        input_stats={},
        frame_annotations={
            raw.frame_ref: FrameAnnotation(
                frame_ref=raw.frame_ref,
                direction="functional",
                isotp_summary="SF len=2",
                uds_summary=None,
                summary="SF len=2",
                addressing_mode="functional",
            )
        },
        conversation_summaries=[],
    )
    result = analyze_trace(bundle, default_config())
    step = result.workflow_steps[0]
    assert step["addressing"] == "functional"
    assert step["sid"] == 0x10
    assert result.frame_annotations[raw.frame_ref].uds_summary.startswith("0x10")


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
