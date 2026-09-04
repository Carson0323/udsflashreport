from __future__ import annotations

"""Flash sequence context for UDS 0x34/0x36/0x37."""

from dataclasses import dataclass, field
from typing import Iterable

from ..models import IsoTpPdu, UdsMessage, UdsTransaction


@dataclass
class FlashBlock:
    block_seq: int
    expected_block_seq: int
    request_length: int
    valid_block_seq: bool
    transaction: UdsTransaction

    @property
    def oversize_against(self) -> int | None:
        return None


@dataclass
class FlashSession:
    start_ts: float | None
    end_ts: float | None
    session_type: str = "programming"
    request_download: UdsTransaction | None = None
    max_block_length: int | None = None
    blocks: list[FlashBlock] = field(default_factory=list)
    expected_bsc: int = 1
    bsc_errors: list[FlashBlock] = field(default_factory=list)
    complete: bool = False

    @property
    def transfer_blocks(self) -> list[FlashBlock]:
        return self.blocks

    @property
    def oversize_blocks(self) -> list[FlashBlock]:
        if self.max_block_length is None:
            return []
        return [block for block in self.blocks if block.request_length > self.max_block_length]


def _request_ts(transaction: UdsTransaction, fallback: float) -> float:
    return transaction.pdu_req.ts_start if transaction.pdu_req is not None else fallback


def _response_ts(transaction: UdsTransaction, fallback: float) -> float:
    return transaction.pdu_resp.ts_end if transaction.pdu_resp is not None else _request_ts(transaction, fallback)


def reconstruct_flash_session(
    transactions: Iterable[UdsTransaction],
    *,
    session_type: str = "programming",
) -> FlashSession | None:
    values = list(transactions)
    if not values:
        return None
    values.sort(key=lambda tx: _request_ts(tx, 0.0))
    download = next((tx for tx in values if tx.request.sid == 0x34), None)
    flash_values = [tx for tx in values if tx.request.sid in {0x34, 0x36, 0x37}]
    if not flash_values:
        return None
    first_ts = _request_ts(flash_values[0], 0.0)
    last_ts = max((_response_ts(tx, first_ts) for tx in flash_values), default=first_ts)
    result = FlashSession(
        start_ts=first_ts,
        end_ts=last_ts,
        session_type=session_type,
        request_download=download,
    )
    if download is not None and download.final_response is not None:
        result.max_block_length = download.final_response.max_block_length

    expected = 1
    for transaction in flash_values:
        message = transaction.request
        if message.sid == 0x36 and message.block_seq is not None:
            observation = FlashBlock(
                block_seq=message.block_seq,
                expected_block_seq=expected,
                request_length=len(message.raw),
                valid_block_seq=message.block_seq == expected,
                transaction=transaction,
            )
            result.blocks.append(observation)
            if not observation.valid_block_seq:
                result.bsc_errors.append(observation)
            expected = (expected + 1) & 0xFF
        elif message.sid == 0x37 and transaction.final_response is not None:
            result.complete = transaction.final_response.is_positive is True
    result.expected_bsc = expected
    return result


def reconstruct_flash_sessions(transactions: Iterable[UdsTransaction]) -> list[FlashSession]:
    values = sorted(transactions, key=lambda tx: _request_ts(tx, 0.0))
    sessions: list[FlashSession] = []
    current: list[UdsTransaction] = []
    for transaction in values:
        if transaction.request.sid == 0x34 and current:
            session = reconstruct_flash_session(current)
            if session is not None:
                sessions.append(session)
            current = []
        if transaction.request.sid in {0x34, 0x36, 0x37}:
            current.append(transaction)
    if current:
        session = reconstruct_flash_session(current)
        if session is not None:
            sessions.append(session)
    return sessions


track_flash_session = reconstruct_flash_session
reconstruct_flash = reconstruct_flash_session


__all__ = [
    "FlashBlock",
    "FlashSession",
    "reconstruct_flash",
    "reconstruct_flash_session",
    "reconstruct_flash_sessions",
    "track_flash_session",
]
