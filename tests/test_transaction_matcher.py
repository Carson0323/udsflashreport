from __future__ import annotations

from flashreport_core.models import TimeoutsConfig
from flashreport_core.uds.decoder import decode_uds
from flashreport_core.uds.pending import TimedUdsMessage
from flashreport_core.uds.transaction_matcher import match_transactions


def timed(ts: float, payload: str) -> TimedUdsMessage:
    return TimedUdsMessage(ts=ts, message=decode_uds(bytes.fromhex(payload)))


def test_unique_request_response_match() -> None:
    result = match_transactions([timed(1.0, "1002")], [timed(1.1, "5002")])
    assert not result.ambiguous
    assert len(result.transactions) == 1
    assert result[0].final_response is not None
    assert result[0].final_response.sid == 0x50


def test_pending_is_retained_until_final_response() -> None:
    result = match_transactions(
        [timed(1.0, "1002")],
        [timed(1.01, "7F1078"), timed(1.2, "5002")],
    )
    transaction = result[0]
    assert len(transaction.pending_events) == 1
    assert transaction.final_response is not None
    assert not result.issues


def test_tester_present_is_auxiliary_and_does_not_make_main_transaction_ambiguous() -> None:
    result = match_transactions(
        [timed(1.0, "3E00"), timed(2.0, "1002")],
        [timed(1.1, "7E00"), timed(2.1, "5002")],
    )
    assert not result.ambiguous
    assert result.input_stats["auxiliary_count"] == 2
    assert len(result.transactions) == 1


def test_interleaved_non_tester_present_requests_are_ambiguous() -> None:
    result = match_transactions(
        [timed(1.0, "1002"), timed(1.1, "22F190")],
        [timed(1.2, "62F190")],
    )
    assert result.ambiguous
    assert result.input_stats["ambiguous"]
    assert all(transaction.ambiguous for transaction in result.transactions)
    assert any(issue.kind == "AMBIGUOUS_UDS_TRANSACTION" for issue in result.issues)


def test_response_without_request_is_ambiguous() -> None:
    result = match_transactions([], [timed(1.0, "5002")])
    assert result.ambiguous
    assert result.issues[0].kind == "AMBIGUOUS_UDS_TRANSACTION"


def test_pending_without_final_can_report_p2_star_timeout() -> None:
    result = match_transactions(
        [timed(1.0, "1002")],
        [timed(1.01, "7F1078")],
        timing=TimeoutsConfig(uds_p2_star_ms=100),
        trace_end_ts=1.2,
    )
    assert any(issue.kind == "pending_timeout" for issue in result.issues)
