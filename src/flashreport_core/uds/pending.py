from __future__ import annotations

"""0x78 pending lifecycle and P2/P2* timeout checks."""

from dataclasses import dataclass
from typing import Iterable

from ..models import TimeoutsConfig, UdsMessage, UdsTransaction


@dataclass(frozen=True)
class TimedUdsMessage:
    ts: float
    message: UdsMessage
    pdu: object | None = None


@dataclass(frozen=True)
class PendingIssue:
    kind: str
    ts: float
    severity: str
    observed: str
    expected: str
    timeout_ms: int


@dataclass
class PendingResult:
    pending_events: list[TimedUdsMessage]
    final_response: TimedUdsMessage | None
    issue: PendingIssue | None

    @property
    def timed_out(self) -> bool:
        return self.issue is not None


def _timed(value: TimedUdsMessage | tuple[float, UdsMessage]) -> TimedUdsMessage:
    if isinstance(value, TimedUdsMessage):
        return value
    return TimedUdsMessage(ts=float(value[0]), message=value[1])


def pending_deadline(
    request_ts: float,
    pending_events: Iterable[TimedUdsMessage | tuple[float, UdsMessage]],
    timing: TimeoutsConfig,
) -> float:
    """Return the P2/P2* deadline, reloading P2* for each observed 0x78."""

    pending = [_timed(value) for value in pending_events]
    if not pending:
        return request_ts + timing.uds_p2_ms / 1000.0
    return pending[-1].ts + timing.uds_p2_star_ms / 1000.0


def check_pending(
    request_ts: float,
    pending_events: Iterable[TimedUdsMessage | tuple[float, UdsMessage]],
    timing: TimeoutsConfig,
    *,
    final_ts: float | None = None,
    trace_end_ts: float | None = None,
) -> PendingIssue | None:
    """Check whether the first response or final response exceeded its timer."""

    pending = [_timed(value) for value in pending_events]
    deadline = pending_deadline(request_ts, pending, timing)
    observed_ts = final_ts if final_ts is not None else trace_end_ts
    if observed_ts is None or observed_ts <= deadline:
        return None
    timeout_ms = timing.uds_p2_star_ms if pending else timing.uds_p2_ms
    phase = "P2*" if pending else "P2"
    return PendingIssue(
        kind="pending_timeout" if pending else "response_timeout",
        ts=deadline,
        severity="error",
        observed=f"no final response before {phase} deadline",
        expected=f"final response within {timeout_ms} ms",
        timeout_ms=timeout_ms,
    )


def evaluate_pending(
    request_ts: float,
    pending_events: Iterable[TimedUdsMessage | tuple[float, UdsMessage]],
    timing: TimeoutsConfig,
    *,
    final_response: TimedUdsMessage | tuple[float, UdsMessage] | None = None,
    trace_end_ts: float | None = None,
) -> PendingResult:
    pending = [_timed(value) for value in pending_events]
    final = _timed(final_response) if final_response is not None else None
    issue = check_pending(
        request_ts,
        pending,
        timing,
        final_ts=final.ts if final is not None else None,
        trace_end_ts=trace_end_ts,
    )
    return PendingResult(pending_events=pending, final_response=final, issue=issue)


def pending_for_transaction(
    transaction: UdsTransaction,
    timing: TimeoutsConfig,
    *,
    request_ts: float,
    final_ts: float | None = None,
    trace_end_ts: float | None = None,
) -> PendingIssue | None:
    return check_pending(
        request_ts,
        [(request_ts, message) for message in transaction.pending_events],
        timing,
        final_ts=final_ts,
        trace_end_ts=trace_end_ts,
    )


check_pending_lifecycle = check_pending
validate_pending = check_pending


__all__ = [
    "PendingIssue",
    "PendingResult",
    "TimedUdsMessage",
    "check_pending",
    "check_pending_lifecycle",
    "evaluate_pending",
    "pending_deadline",
    "pending_for_transaction",
    "validate_pending",
]
