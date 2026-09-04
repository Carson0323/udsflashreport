from __future__ import annotations

"""Best-effort diagnostic session reconstruction."""

from dataclasses import dataclass
from typing import Iterable

from ..models import UdsMessage, UdsTransaction


SESSION_NAMES = {
    0x01: "default",
    0x02: "programming",
    0x03: "extended",
}


@dataclass
class DiagnosticSession:
    session_type: str
    session_id: int | None
    start_ts: float
    end_ts: float
    reason: str = "trace_start"

    @property
    def name(self) -> str:
        return self.session_type


def _transaction_ts(transaction: UdsTransaction, fallback: float) -> tuple[float, float]:
    start = transaction.pdu_req.ts_start if transaction.pdu_req is not None else fallback
    end = (
        transaction.pdu_resp.ts_end
        if transaction.pdu_resp is not None
        else transaction.pdu_req.ts_end
        if transaction.pdu_req is not None
        else start
    )
    return start, end


def _coerce_transactions(values: Iterable[UdsTransaction | UdsMessage]) -> list[tuple[float, float, UdsMessage, UdsMessage | None]]:
    result = []
    for index, value in enumerate(values):
        if isinstance(value, UdsTransaction):
            start, end = _transaction_ts(value, float(index))
            result.append((start, end, value.request, value.final_response))
        elif isinstance(value, UdsMessage):
            result.append((float(index), float(index), value, None))
        else:
            raise TypeError("session input must contain UdsTransaction or UdsMessage")
    return sorted(result, key=lambda item: item[0])


def reconstruct_sessions(
    values: Iterable[UdsTransaction | UdsMessage],
    *,
    s3_timeout_ms: int = 5000,
) -> list[DiagnosticSession]:
    events = _coerce_transactions(values)
    if not events:
        return []
    timeout_s = s3_timeout_ms / 1000.0
    first_ts = events[0][0]
    current = DiagnosticSession("default", 0x01, first_ts, first_ts, "trace_start")
    sessions: list[DiagnosticSession] = []
    previous_activity = first_ts

    for start, end, request, response in events:
        if start - previous_activity > timeout_s:
            current.end_ts = previous_activity
            sessions.append(current)
            current = DiagnosticSession("default", 0x01, start, start, "s3_timeout")

        base_sid = request.sid
        positive = response is not None and response.is_positive is True
        if base_sid == 0x10 and request.subfunction is not None and positive:
            session_id = request.subfunction
            session_type = SESSION_NAMES.get(session_id, f"unknown_0x{session_id:02X}")
            current.end_ts = end
            sessions.append(current)
            current = DiagnosticSession(session_type, session_id, end, end, "session_control")
        elif base_sid == 0x11 and positive:
            current.end_ts = end
            sessions.append(current)
            current = DiagnosticSession("default", 0x01, end, end, "ecu_reset")
        else:
            current.end_ts = max(current.end_ts, end)
        previous_activity = max(previous_activity, end)

    current.end_ts = max(current.end_ts, previous_activity)
    sessions.append(current)
    return sessions


def session_at(sessions: Iterable[DiagnosticSession], ts: float) -> DiagnosticSession | None:
    for session in sessions:
        if session.start_ts <= ts <= session.end_ts:
            return session
    return None


reconstruct_diagnostic_sessions = reconstruct_sessions
track_sessions = reconstruct_sessions


__all__ = [
    "DiagnosticSession",
    "reconstruct_diagnostic_sessions",
    "reconstruct_sessions",
    "session_at",
    "track_sessions",
]
