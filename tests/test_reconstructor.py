from __future__ import annotations

from flashreport_core.addressing import make_pair_key
from flashreport_core.isotp.events import (
    build_conversations,
    decode_event,
    eventize_frames,
)
from flashreport_core.isotp.reconstructor import reconstruct_pdus
from flashreport_core.models import AddressedFrame, RawFrame, TimeoutsConfig


PAIR_KEY = make_pair_key(1, 0x18DA10F1, 0x18DAF110)


def frame(
    data: bytes,
    *,
    ts: float = 1.0,
    line: int = 1,
    direction: str = "tester->ecu",
    is_fd: bool = False,
    metadata: dict | None = None,
) -> AddressedFrame:
    raw = RawFrame(
        ts_seconds=ts,
        ts_display=f"{ts:.6f}",
        source_ts_metadata=metadata or {},
        can_id=0x18DA10F1 if direction == "tester->ecu" else 0x18DAF110,
        is_extended=True,
        channel=1,
        is_fd=is_fd,
        dlc=len(data),
        data=data,
        source="asc",
        line_no=line,
    )
    return AddressedFrame(**raw.__dict__, role=direction, pair_key=PAIR_KEY)


def event(data: bytes, **kwargs):
    decoded, issue = decode_event(frame(data, **kwargs))
    assert issue is None, issue
    assert decoded is not None
    return decoded


def test_sf_reconstructs_payload() -> None:
    pdus = reconstruct_pdus([event(bytes.fromhex("03504142"))])
    assert len(pdus) == 1
    assert pdus[0].pci == "single"
    assert pdus[0].payload == b"PAB"
    assert not pdus[0].incomplete


def test_ff_and_all_cf_reconstructs_without_fc() -> None:
    pdus = reconstruct_pdus(
        [
            event(bytes.fromhex("100D313233343536"), line=1),
            event(bytes.fromhex("213738393A3B3C3D"), ts=1.001, line=2),
        ]
    )
    assert pdus[0].payload == b"123456789:;<="
    assert pdus[0].frames[0].frame_ref == "asc:1"
    assert not pdus[0].incomplete


def test_missing_fc_does_not_discard_reconstructable_pdu() -> None:
    result = eventize_frames(
        [
            frame(bytes.fromhex("100C313233343536"), line=1),
            frame(bytes.fromhex("213738393A3B3C3D"), ts=1.001, line=2),
        ]
    )
    assert not result.issues
    assert not reconstruct_pdus(result.events)[0].incomplete


def test_missing_cf_marks_pdu_incomplete() -> None:
    pdu = reconstruct_pdus([event(bytes.fromhex("100C313233343536"))])[0]
    assert pdu.incomplete
    assert pdu.incomplete_reason == "missing_cf"
    assert pdu.payload == b"123456"


def test_sn_gap_marks_pdu_incomplete() -> None:
    pdus = reconstruct_pdus(
        [
            event(bytes.fromhex("100C313233343536"), line=1),
            event(bytes.fromhex("223738393A3B3C3D"), ts=1.001, line=2),
        ]
    )
    assert pdus[0].incomplete
    assert pdus[0].incomplete_reason == "sn_gap"
    assert any(issue.kind == "sn_gap" for issue in pdus[0].issues)


def test_sn_wrap_from_f_to_zero_is_valid() -> None:
    total = 6 + 16 * 7 + 1
    events = [event(bytes([0x10 | (total >> 8), total & 0xFF, *b"ABCDEF"]), line=1)]
    for index in range(16):
        events.append(event(bytes([0x20 | ((index + 1) & 0x0F), *b"1234567"]), ts=1 + index * 0.001, line=index + 2))
    events.append(event(bytes.fromhex("2101"), ts=1.020, line=18))
    pdu = reconstruct_pdus(events)[0]
    assert not pdu.incomplete
    assert len(pdu.payload or b"") == total


def test_timeout_gap_marks_pdu_incomplete() -> None:
    pdus = reconstruct_pdus(
        [
            event(bytes.fromhex("100C313233343536"), line=1),
            event(bytes.fromhex("213738393A3B3C3D"), ts=2.1, line=2),
        ],
        timing=TimeoutsConfig(isotp_cf_ms=100),
    )
    assert pdus[0].incomplete
    assert pdus[0].incomplete_reason == "timeout_cf_gap"
    assert pdus[0].issues[0].kind == "timeout_cf_gap"


def test_fc_wait_and_overflow_are_eventized() -> None:
    wait, wait_issue = decode_event(frame(bytes.fromhex("310500"), direction="ecu->tester"))
    overflow, overflow_issue = decode_event(frame(bytes.fromhex("320000"), direction="ecu->tester"))
    assert wait_issue is None and overflow_issue is None
    assert wait is not None and wait.kind == "fc" and wait.fs == 1
    assert overflow is not None and overflow.kind == "fc" and overflow.fs == 2


def test_non_isotp_pci_is_skipped_with_diagnostic() -> None:
    result = eventize_frames([frame(bytes.fromhex("F050"))])
    assert not result.events
    assert result.issues[0].kind == "unsupported_pci"


def test_can_fd_uses_record_flag_not_dlc_inference() -> None:
    result = eventize_frames([frame(bytes.fromhex("0250020000000000"), is_fd=True)])
    assert not result.events
    assert result.issues[0].kind == "unsupported_can_fd"
    assert eventize_frames([frame(bytes.fromhex("0250020000000000"))]).events[0].kind == "sf"


def test_explicit_extended_addressing_is_unsupported() -> None:
    result = eventize_frames(
        [frame(bytes.fromhex("F1025002"), metadata={"addressing_mode": "extended"})]
    )
    assert result.issues[0].kind == "unsupported_addressing_mode"


def test_unknown_pci_is_skipped() -> None:
    result = eventize_frames([frame(bytes.fromhex("4F55000000000000"))])
    assert not result.events
    assert result.issues[0].kind == "unsupported_pci"


def test_direction_isolation_keeps_fc_out_of_sender_pdu_frames() -> None:
    addressed = [
        frame(bytes.fromhex("100C313233343536"), line=1, ts=1.0),
        frame(bytes.fromhex("300800"), line=2, ts=1.001, direction="ecu->tester"),
        frame(bytes.fromhex("213738393A3B3C3D"), line=3, ts=1.002),
    ]
    conv = build_conversations(addressed)[0]
    assert len(conv.pdus) == 1
    assert [item.role for item in conv.pdus[0].frames] == ["tester->ecu", "tester->ecu"]
    assert [item.kind for item in conv.ecu_to_tester_events] == ["fc"]


def test_new_single_frame_starts_after_incomplete_multi_frame() -> None:
    pdus = reconstruct_pdus(
        [
            event(bytes.fromhex("100C313233343536"), line=1),
            event(bytes.fromhex("0358595A"), ts=1.001, line=2),
        ]
    )
    assert pdus[0].incomplete_reason == "new_pdu_before_completion"
    assert pdus[1].payload == b"XYZ"
