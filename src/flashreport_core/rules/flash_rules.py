from __future__ import annotations

"""Registered flash-sequence attribution evaluator."""

from .context import RuleContext, build_finding, pdu_evidence


def oversize_or_bsc_error(issue, ctx: RuleContext):
    block = ctx.flash_block
    session = ctx.flash_session
    if block is None or session is None:
        return None
    oversize = (
        session.max_block_length is not None
        and block.request_length > session.max_block_length
    )
    bsc_error = not block.valid_block_seq
    if not oversize and not bsc_error:
        return None

    transaction = block.transaction
    request_ts = (
        transaction.pdu_req.ts_end
        if transaction.pdu_req is not None
        else session.start_ts or 0.0
    )
    detected_ts = (
        transaction.pdu_resp.ts_end
        if transaction.pdu_resp is not None
        else request_ts
    )
    evidence = pdu_evidence(
        transaction.pdu_req,
        f"TransferData 0x36 BSC={block.block_seq} length={block.request_length}",
    )
    if oversize and session.request_download is not None:
        evidence = pdu_evidence(
            session.request_download.pdu_resp,
            f"RequestDownload 0x74 maxBlockLength={session.max_block_length}",
        ) + evidence
    elif transaction.pdu_resp is not None:
        evidence.extend(
            pdu_evidence(
                transaction.pdu_resp,
                f"TransferData response for BSC={block.block_seq}",
            )
        )

    # A wrong BSC is still evidence-backed when the response is absent: use
    # the immediately preceding transfer block as the expected-counter anchor.
    if len(evidence) < 2 and session.blocks:
        previous = next(
            (
                candidate
                for candidate in reversed(session.blocks)
                if candidate is not block and candidate.block_seq == block.expected_block_seq
            ),
            None,
        )
        if previous is not None:
            evidence.extend(
                pdu_evidence(
                    previous.transaction.pdu_req,
                    f"previous TransferData expected BSC={previous.block_seq}",
                )
            )
    if len(evidence) < 2:
        return None

    violation = []
    if oversize:
        violation.append("oversize")
    if bsc_error:
        violation.append("bsc_error")
    expected = (
        f"TransferData request length <= {session.max_block_length}"
        if oversize
        else f"blockSequenceCounter={block.expected_block_seq}"
    )
    observed = (
        f"TransferData request length={block.request_length}"
        if oversize
        else f"blockSequenceCounter={block.block_seq}"
    )
    return build_finding(
        ctx=ctx,
        finding_id="FLASH-001",
        layer="FLASH",
        category="oversize_or_bsc_error",
        deviation_ts=request_ts,
        detected_ts=detected_ts,
        observed=observed,
        expected=expected,
        suspected_side="tester",
        base_confidence="high",
        detail={
            "violations": violation,
            "request_length": block.request_length,
            "max_block_length": session.max_block_length,
            "block_seq": block.block_seq,
            "expected_block_seq": block.expected_block_seq,
        },
        evidence=evidence,
        session=ctx.session_name,
        service=transaction.request.service_name,
    )


__all__ = ["oversize_or_bsc_error"]
