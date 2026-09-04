from __future__ import annotations

from flashreport_core.addressing import make_pair_key
from flashreport_core.isotp.events import decode_event
from flashreport_core.isotp.reconstructor import reconstruct_pdus
from flashreport_core.isotp.validator import stmin_to_seconds, validate_conversation
from flashreport_core.models import (
    AddressedFrame,
    IsoTpConversation,
    RawFrame,
    TraceQuality,
    TraceWindow,
    TimeoutsConfig,
)


PAIR_KEY = make_pair_key(1, 0x18DA10F1, 0x18DAF110)


def frame(
    data: bytes,
    *,
    ts: float,
    line: int,
    direction: str = "tester->ecu",
) -> AddressedFrame:
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
        source="asc",
        line_no=line,
    )
    return AddressedFrame(**raw.__dict__, role=direction, pair_key=PAIR_KEY)


def event(data: bytes, *, ts: float, line: int, direction: str = "tester->ecu"):
    result, issue = decode_event(frame(data, ts=ts, line=line, direction=direction))
    assert issue is None, issue
    assert result is not None
    return result


def conversation(tester: list, ecu: list) -> IsoTpConversation:
    all_events = tester + ecu
    quality = TraceQuality(
        start_ts=0.0,
        end_ts=max((item.ts for item in all_events), default=10.0) + 2.0,
        has_capture_gap=False,
        dropped_frame_count=0,
        source_channels=[1],
        filter_state_known=True,
        completeness="verified",
    )
    pdus = reconstruct_pdus(tester, pair_key=PAIR_KEY, direction="tester->ecu")
    pdus.extend(reconstruct_pdus(ecu, pair_key=PAIR_KEY, direction="ecu->tester"))
    return IsoTpConversation(
        pair_key=PAIR_KEY,
        tester_to_ecu_events=tester,
        ecu_to_tester_events=ecu,
        pdus=pdus,
        trace_window=TraceWindow(start_ts=0.0, end_ts=quality.end_ts, coverage_ok=True),
    )


TIMING = TimeoutsConfig(isotp_fc_ms=100, isotp_cf_ms=100)


def quality() -> TraceQuality:
    return TraceQuality(
        start_ts=0.0,
        end_ts=10.0,
        has_capture_gap=False,
        dropped_frame_count=0,
        source_channels=[1],
        filter_state_known=True,
        completeness="verified",
    )


def validate(tester: list, ecu: list):
    conv = conversation(tester, ecu)
    return validate_conversation(conv, TIMING, quality())


def test_missing_fc_after_ff() -> None:
    issues = validate([event(bytes.fromhex("100C313233343536"), ts=1.0, line=1)], [])
    assert "missing_fc_after_ff" in [issue.kind for issue in issues]


def test_bs0_no_extra_fc() -> None:
    tester = [
        event(bytes.fromhex("100C313233343536"), ts=1.0, line=1),
        event(bytes.fromhex("213738393A3B3C3D"), ts=1.01, line=3),
    ]
    ecu = [event(bytes.fromhex("300000"), ts=1.001, line=2, direction="ecu->tester")]
    assert [issue.kind for issue in validate(tester, ecu)] == []


def test_bs8_requires_second_fc() -> None:
    tester = [event(bytes.fromhex("1040313233343536"), ts=1.0, line=1)]
    tester.extend(
        event(bytes([0x20 | index, *b"1234567"]), ts=1.01 + index * 0.001, line=3 + index)
        for index in range(8)
    )
    tester.append(event(bytes.fromhex("29010203040506"), ts=1.019, line=20))
    ecu = [
        event(bytes.fromhex("300800"), ts=1.001, line=2, direction="ecu->tester"),
        event(bytes.fromhex("300800"), ts=1.0195, line=21, direction="ecu->tester"),
    ]
    assert "missing_fc_after_block" not in [issue.kind for issue in validate(tester, ecu)]


def test_missing_fc_after_block() -> None:
    tester = [event(bytes.fromhex("1040313233343536"), ts=1.0, line=1)]
    tester.extend(
        event(bytes([0x20 | index, *b"1234567"]), ts=1.01 + index * 0.001, line=3 + index)
        for index in range(8)
    )
    ecu = [event(bytes.fromhex("300800"), ts=1.001, line=2, direction="ecu->tester")]
    assert "missing_fc_after_block" in [issue.kind for issue in validate(tester, ecu)]


def test_pdu_end_does_not_require_next_fc() -> None:
    tester = [event(bytes.fromhex("100E313233343536"), ts=1.0, line=1)]
    tester.extend(
        event(bytes([0x20 | index, *b"1234567"]), ts=1.01 + index * 0.001, line=3 + index)
        for index in range(2)
    )
    ecu = [event(bytes.fromhex("300200"), ts=1.001, line=2, direction="ecu->tester")]
    assert "missing_fc_after_block" not in [issue.kind for issue in validate(tester, ecu)]


def test_cf_before_cts_is_transport_error() -> None:
    tester = [
        event(bytes.fromhex("100C313233343536"), ts=1.0, line=1),
        event(bytes.fromhex("213738393A3B3C3D"), ts=1.001, line=2),
    ]
    ecu = [event(bytes.fromhex("300800"), ts=1.002, line=3, direction="ecu->tester")]
    assert "cf_before_fc" in [issue.kind for issue in validate(tester, ecu)]


def test_cf_after_cts_missing() -> None:
    tester = [event(bytes.fromhex("100C313233343536"), ts=1.0, line=1)]
    ecu = [event(bytes.fromhex("300800"), ts=1.001, line=2, direction="ecu->tester")]
    assert "cf_after_cts_missing" in [issue.kind for issue in validate(tester, ecu)]


def test_sn_gap_is_reported_by_validator() -> None:
    tester = [
        event(bytes.fromhex("100C313233343536"), ts=1.0, line=1),
        event(bytes.fromhex("223738393A3B3C3D"), ts=1.01, line=3),
    ]
    ecu = [event(bytes.fromhex("300000"), ts=1.001, line=2, direction="ecu->tester")]
    assert "sn_gap" in [issue.kind for issue in validate(tester, ecu)]


def test_stmin_violation_is_warning() -> None:
    tester = [
        event(bytes.fromhex("100C313233343536"), ts=1.0, line=1),
        event(bytes.fromhex("213738393A3B3C3D"), ts=1.01, line=3),
        event(bytes.fromhex("22414243444546"), ts=1.011, line=4),
    ]
    ecu = [event(bytes.fromhex("300805"), ts=1.001, line=2, direction="ecu->tester")]
    issues = validate(tester, ecu)
    assert any(issue.kind == "stmin_violation" and issue.severity == "warning" for issue in issues)


def test_stmin_reserved_values_are_not_interpreted_as_time() -> None:
    assert stmin_to_seconds(0x80) is None
    assert stmin_to_seconds(0xF0) is None
    assert stmin_to_seconds(0xF1) == 0.0001
    tester = [
        event(bytes.fromhex("100C313233343536"), ts=1.0, line=1),
        event(bytes.fromhex("213738393A3B3C3D"), ts=1.01, line=3),
    ]
    ecu = [event(bytes.fromhex("300880"), ts=1.001, line=2, direction="ecu->tester")]
    assert "stmin_reserved" in [issue.kind for issue in validate(tester, ecu)]


def test_wait_timeout_and_overflow() -> None:
    tester = [event(bytes.fromhex("100C313233343536"), ts=1.0, line=1)]
    ecu_wait = [event(bytes.fromhex("310000"), ts=1.001, line=2, direction="ecu->tester")]
    assert "wait_timeout" in [issue.kind for issue in validate(tester, ecu_wait)]
    ecu_overflow = [event(bytes.fromhex("320000"), ts=1.001, line=2, direction="ecu->tester")]
    assert "overflow" in [issue.kind for issue in validate(tester, ecu_overflow)]


def test_late_cf_reports_timeout_gap() -> None:
    tester = [
        event(bytes.fromhex("100C313233343536"), ts=1.0, line=1),
        event(bytes.fromhex("213738393A3B3C3D"), ts=1.01, line=3),
        event(bytes.fromhex("22414243444546"), ts=2.0, line=4),
    ]
    ecu = [event(bytes.fromhex("300000"), ts=1.001, line=2, direction="ecu->tester")]
    assert "timeout_cf_gap" in [issue.kind for issue in validate(tester, ecu)]
