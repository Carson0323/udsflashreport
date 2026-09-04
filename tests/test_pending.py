from __future__ import annotations

from flashreport_core.models import TimeoutsConfig
from flashreport_core.uds.decoder import decode_uds
from flashreport_core.uds.pending import (
    TimedUdsMessage,
    check_pending,
    evaluate_pending,
    pending_deadline,
)


TIMING = TimeoutsConfig(uds_p2_ms=50, uds_p2_star_ms=5000)


def timed(ts: float, payload: str) -> TimedUdsMessage:
    return TimedUdsMessage(ts=ts, message=decode_uds(bytes.fromhex(payload)))


def test_no_pending_uses_p2_and_final_before_deadline_is_valid() -> None:
    assert pending_deadline(1.0, [], TIMING) == 1.05
    assert check_pending(1.0, [], TIMING, final_ts=1.049) is None


def test_no_pending_timeout_is_p2_response_timeout() -> None:
    issue = check_pending(1.0, [], TIMING, trace_end_ts=1.051)
    assert issue is not None
    assert issue.kind == "response_timeout"
    assert issue.timeout_ms == 50


def test_pending_switches_to_p2_star_and_reloads_for_each_pending() -> None:
    pending = [timed(1.01, "7F1078"), timed(5.0, "7F1078")]
    assert pending_deadline(1.0, pending, TIMING) == 10.0
    assert check_pending(1.0, pending, TIMING, final_ts=9.9) is None
    issue = check_pending(1.0, pending, TIMING, trace_end_ts=10.001)
    assert issue is not None and issue.kind == "pending_timeout"
    assert issue.timeout_ms == 5000


def test_evaluate_pending_returns_messages_and_final() -> None:
    result = evaluate_pending(
        1.0,
        [timed(1.01, "7F1078")],
        TIMING,
        final_response=timed(1.2, "5001"),
    )
    assert len(result.pending_events) == 1
    assert result.final_response is not None
    assert result.issue is None
