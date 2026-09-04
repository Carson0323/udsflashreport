"""Compatibility import for the public UDS transaction matcher."""

from .transaction_matcher import (
    TransactionIssue,
    TransactionMatchResult,
    match,
    match_conversation,
    match_transactions,
    match_uds_transactions,
    transaction_matcher,
)

__all__ = [
    "TransactionIssue",
    "TransactionMatchResult",
    "match",
    "match_conversation",
    "match_transactions",
    "match_uds_transactions",
    "transaction_matcher",
]
