from __future__ import annotations

"""Deterministic request/response matching for one addressed conversation."""

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..models import IsoTpConversation, IsoTpPdu, UdsMessage, UdsTransaction
from .decoder import decode_uds
from .pending import PendingIssue, TimedUdsMessage, check_pending


@dataclass(frozen=True)
class TransactionIssue:
    kind: str
    ts: float
    observed: str
    expected: str


@dataclass
class TransactionMatchResult:
    transactions: list[UdsTransaction]
    auxiliary: list[TimedUdsMessage]
    ambiguous: bool
    issues: list[TransactionIssue | PendingIssue]
    input_stats: dict

    def __iter__(self):
        return iter(self.transactions)

    def __len__(self) -> int:
        return len(self.transactions)

    def __getitem__(self, index: int) -> UdsTransaction:
        return self.transactions[index]


@dataclass
class _RequestState:
    timed: TimedUdsMessage
    transaction: UdsTransaction
    ambiguous: bool = False
    pending_timed: list[TimedUdsMessage] | None = None


def _coerce_item(value: IsoTpPdu | UdsMessage | TimedUdsMessage, index: int) -> TimedUdsMessage:
    if isinstance(value, TimedUdsMessage):
        return value
    if isinstance(value, IsoTpPdu):
        return TimedUdsMessage(ts=value.ts_start, message=decode_uds(value), pdu=value)
    if isinstance(value, UdsMessage):
        return TimedUdsMessage(ts=float(index), message=value)
    raise TypeError("matcher inputs must be IsoTpPdu, UdsMessage, or TimedUdsMessage")


def _coerce_items(values: Iterable[IsoTpPdu | UdsMessage | TimedUdsMessage]) -> list[TimedUdsMessage]:
    return sorted((_coerce_item(value, index) for index, value in enumerate(values)), key=lambda item: item.ts)


def _is_tester_present(message: UdsMessage) -> bool:
    return message.sid == 0x3E


def _response_targets_tester_present(message: UdsMessage) -> bool:
    return message.sid == 0x7E or (message.sid == 0x7F and message.raw[1:2] == b"\x3E")


def match_transactions(
    request_pdus: Iterable[IsoTpPdu | UdsMessage | TimedUdsMessage],
    response_pdus: Iterable[IsoTpPdu | UdsMessage | TimedUdsMessage],
    *,
    pair_key: str | None = None,
    timing=None,
    trace_end_ts: float | None = None,
) -> TransactionMatchResult:
    """Match non-TesterPresent requests, retaining ambiguity explicitly."""

    requests = _coerce_items(request_pdus)
    responses = _coerce_items(response_pdus)
    pair_key = pair_key or next(
        (item.pdu.pair_key for item in requests + responses if isinstance(item.pdu, IsoTpPdu)),
        "",
    )
    combined = sorted(
        [(item.ts, 0, item) for item in requests] + [(item.ts, 1, item) for item in responses],
        key=lambda row: (row[0], row[1]),
    )
    active: list[_RequestState] = []
    transactions: list[UdsTransaction] = []
    auxiliary: list[TimedUdsMessage] = []
    issues: list[TransactionIssue | PendingIssue] = []
    ambiguous = False
    states: list[_RequestState] = []

    for _, kind, item in combined:
        message = item.message
        if kind == 0:
            if _is_tester_present(message):
                auxiliary.append(item)
                continue
            if active:
                ambiguous = True
                for state in active:
                    state.ambiguous = True
                    state.transaction.ambiguous = True
            transaction = UdsTransaction(
                request=message,
                pending_events=[],
                final_response=None,
                pdu_req=item.pdu if isinstance(item.pdu, IsoTpPdu) else None,
                pdu_resp=None,
                ambiguous=bool(active),
            )
            state = _RequestState(
                timed=item,
                transaction=transaction,
                ambiguous=bool(active),
                pending_timed=[],
            )
            active.append(state)
            states.append(state)
            transactions.append(transaction)
            continue

        if _response_targets_tester_present(message):
            auxiliary.append(item)
            continue
        if message.pending:
            if not active:
                ambiguous = True
                issues.append(
                    TransactionIssue(
                        kind="AMBIGUOUS_UDS_TRANSACTION",
                        ts=item.ts,
                        observed="pending response has no outstanding request",
                        expected="one unique non-TesterPresent request",
                    )
                )
                continue
            if len(active) > 1:
                ambiguous = True
                for state in active:
                    state.ambiguous = True
                    state.transaction.ambiguous = True
            state = max(active, key=lambda candidate: candidate.timed.ts)
            state.transaction.pending_events.append(message)
            state.pending_timed.append(item)
            continue

        if not active:
            ambiguous = True
            issues.append(
                TransactionIssue(
                    kind="AMBIGUOUS_UDS_TRANSACTION",
                    ts=item.ts,
                    observed="response has no outstanding request",
                    expected="one unique non-TesterPresent request",
                )
            )
            continue
        if len(active) > 1:
            ambiguous = True
            for state in active:
                state.ambiguous = True
                state.transaction.ambiguous = True
        state = max(active, key=lambda candidate: candidate.timed.ts)
        state.transaction.final_response = message
        state.transaction.pdu_resp = item.pdu if isinstance(item.pdu, IsoTpPdu) else None
        active.remove(state)

    if ambiguous and not any(
        isinstance(issue, TransactionIssue) and issue.kind == "AMBIGUOUS_UDS_TRANSACTION"
        for issue in issues
    ):
        first_ts = min((item.ts for item in requests + responses), default=0.0)
        issues.insert(
            0,
            TransactionIssue(
                kind="AMBIGUOUS_UDS_TRANSACTION",
                ts=first_ts,
                observed="request/response interval cannot be uniquely paired",
                expected="at most one outstanding non-TesterPresent request",
            ),
        )

    if timing is not None:
        end_ts = trace_end_ts
        if end_ts is None:
            end_ts = max((item.ts for item in requests + responses), default=0.0)
        for state in states:
            if state.transaction.final_response is not None or not state.transaction.pending_events:
                continue
            issue = check_pending(
                state.timed.ts,
                state.pending_timed or [],
                timing,
                trace_end_ts=end_ts,
            )
            if issue is not None:
                issues.append(issue)

    stats = {
        "ambiguous": ambiguous,
        "ambiguous_count": int(ambiguous),
        "transaction_count": len(transactions),
        "auxiliary_count": len(auxiliary),
        "issue_count": len(issues),
    }
    return TransactionMatchResult(
        transactions=transactions,
        auxiliary=auxiliary,
        ambiguous=ambiguous,
        issues=issues,
        input_stats=stats,
    )


def match_conversation(
    conv: IsoTpConversation,
    *,
    timing=None,
    trace_end_ts: float | None = None,
) -> TransactionMatchResult:
    return match_transactions(
        [pdu for pdu in conv.pdus if pdu.direction == "tester->ecu"],
        [pdu for pdu in conv.pdus if pdu.direction == "ecu->tester"],
        pair_key=conv.pair_key,
        timing=timing,
        trace_end_ts=trace_end_ts,
    )


transaction_matcher = match_transactions
match = match_transactions
match_uds_transactions = match_transactions


__all__ = [
    "TransactionIssue",
    "TransactionMatchResult",
    "match",
    "match_conversation",
    "match_transactions",
    "match_uds_transactions",
    "transaction_matcher",
]
