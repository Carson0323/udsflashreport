from __future__ import annotations

"""Human-readable UDS/flash workflow projection / 刷写流程投影。"""

from typing import Any

from .models import AppConfig, IsoTpConversation, RawFrame, TraceBundle, UdsMessage, UdsTransaction
from .uds.decoder import decode_uds, parse_download_fields
from .uds.transaction_matcher import match_conversation


def _spaced_hex(data: bytes) -> str:
    return " ".join(f"{value:02X}" for value in data) or "—"


def _ascii_preview(data: bytes) -> str:
    return "".join(chr(value) if 0x20 <= value <= 0x7E else "." for value in data) or "—"


def _hex(value: int | None, width: int = 0) -> str:
    if value is None:
        return "—"
    return f"0x{value:0{width}X}" if width else f"0x{value:X}"


def _download_fields(raw: bytes) -> tuple[int | None, int | None]:
    return parse_download_fields(raw)


def _routine_fields(raw: bytes) -> tuple[int | None, bytes]:
    if len(raw) < 4 or raw[0] != 0x31:
        return None, b""
    return int.from_bytes(raw[2:4], "big"), raw[4:]


def _message_detail(message: UdsMessage) -> dict[str, Any]:
    raw = bytes(message.raw)
    raw_display = _spaced_hex(raw)
    if message.sid == 0x36:
        raw_display = (
            f"36 BSC={message.block_seq:02X} payload_bytes={max(0, len(raw) - 2)}"
            if message.block_seq is not None
            else f"36 payload_bytes={max(0, len(raw) - 2)}"
        )
    detail: dict[str, Any] = {
        "sid": message.sid,
        "service_name": message.service_name,
        "subfunction": message.subfunction,
        "did": message.did,
        "block_seq": message.block_seq,
        "raw": raw_display,
    }
    if message.sid == 0x34:
        address, length = _download_fields(raw)
        detail.update({"start_address": address, "transfer_length": length})
    if message.sid == 0x31:
        routine_id, parameters = _routine_fields(raw)
        detail.update(
            {
                "routine_id": routine_id,
                "routine_parameters": _spaced_hex(parameters),
                "routine_ascii": _ascii_preview(parameters),
            }
        )
    if message.sid == 0x36:
        detail["transfer_data_length"] = max(0, len(raw) - 2)
    if message.sid in {0x22, 0x2E, 0x62, 0x6E} and len(raw) >= 3:
        detail["did_bytes"] = _spaced_hex(raw[1:3])
    if message.sid in {0x2E, 0x6E} and len(raw) > 3:
        detail["write_data"] = _spaced_hex(raw[3:])
        detail["write_ascii"] = _ascii_preview(raw[3:])
    if message.sid in {0x22, 0x62} and len(raw) > 3:
        detail["read_data"] = _spaced_hex(raw[3:])
        detail["read_ascii"] = _ascii_preview(raw[3:])
    if message.sid not in {0x36, 0x22, 0x2E, 0x62, 0x6E} and len(raw) > 1:
        detail["service_data"] = _spaced_hex(raw[1:])
    return detail


def _step_detail(request: UdsMessage, response: UdsMessage | None) -> str:
    detail = _message_detail(request)
    parts = [
        f"0x{request.sid:02X} {request.service_name or 'unknown'}"
        if request.sid is not None
        else "unknown service"
    ]
    if request.subfunction is not None:
        parts.append(f"SubFunction={_hex(request.subfunction, 2)}")
    if request.did is not None:
        parts.append(f"DID={_hex(request.did, 4)}")
        if detail.get("did_bytes"):
            parts.append(f"DID bytes={detail['did_bytes']}")
    if request.sid == 0x2E:
        parts.append(f"write_data={detail.get('write_data') or '—'}")
        parts.append(f"ASCII={detail.get('write_ascii') or '—'}")
    if request.sid == 0x34:
        parts.append(f"start={_hex(detail['start_address'])}")
        parts.append(f"length={_hex(detail['transfer_length'])}")
    if request.sid == 0x36:
        parts.append(f"BSC={_hex(request.block_seq, 2)}")
        parts.append(f"payload_bytes={detail['transfer_data_length']}")
    if request.sid == 0x31:
        parts.append(f"RoutineID={_hex(detail['routine_id'], 4)}")
        parts.append(f"params={detail['routine_parameters'] or '—'}")
        parts.append(f"ASCII={detail.get('routine_ascii') or '—'}")
    if request.sid not in {0x22, 0x2E, 0x31, 0x34, 0x36} and detail.get("service_data"):
        parts.append(f"data={detail['service_data']}")
    if response is None:
        parts.append("response=missing")
    elif response.is_positive is False:
        parts.append(
            f"response=NRC {_hex(response.nrc, 2)} ({response.nrc_text or 'unknownNRC'})"
        )
    else:
        parts.append(
            f"response=0x{response.sid:02X}"
            if response.sid is not None
            else "response=positive"
        )
    if request.sid == 0x22 and response is not None:
        response_detail = _message_detail(response)
        if response_detail.get("did_bytes"):
            parts.append(f"DID bytes={response_detail['did_bytes']}")
        parts.append(f"read_data={response_detail.get('read_data') or '—'}")
        parts.append(f"ASCII={response_detail.get('read_ascii') or '—'}")
    return " · ".join(parts)


def _frame_refs(transaction: UdsTransaction) -> tuple[str, ...]:
    refs: list[str] = []
    for pdu in (transaction.pdu_req, transaction.pdu_resp):
        if pdu is not None and pdu.frames:
            refs.append(pdu.frames[0].frame_ref)
            if pdu.frames[-1].frame_ref != pdu.frames[0].frame_ref:
                refs.append(pdu.frames[-1].frame_ref)
    return tuple(refs)


def _transaction_step(transaction: UdsTransaction, index: int, pair_key: str) -> dict[str, Any]:
    request = transaction.request
    response = transaction.final_response
    start = transaction.pdu_req.ts_start if transaction.pdu_req is not None else float(index)
    end = (
        transaction.pdu_resp.ts_end
        if transaction.pdu_resp is not None
        else transaction.pdu_req.ts_end
        if transaction.pdu_req is not None
        else start
    )
    status_key = (
        "no_response"
        if response is None
        else "negative"
        if response.is_positive is False
        else "positive"
    )
    return {
        "step_index": index,
        "ts_start": start,
        "ts_end": end,
        "direction": "tester->ecu",
        "addressing": "physical",
        "pair_key": pair_key,
        "sid": request.sid,
        "service_name": request.service_name,
        "subfunction": request.subfunction,
        "did": request.did,
        "block_seq": request.block_seq,
        "status_key": status_key,
        "request_raw": _message_detail(request)["raw"],
        "response_raw": _message_detail(response)["raw"] if response is not None else None,
        "response_fields": _message_detail(response) if response is not None else {},
        "detail": _step_detail(request, response),
        "fields": _message_detail(request),
        "evidence_frame_refs": _frame_refs(transaction),
        "session": None,
    }


def _functional_payload(frame: RawFrame) -> bytes | None:
    if not frame.data:
        return None
    pci_type = frame.data[0] >> 4
    if pci_type == 0x0:
        length = frame.data[0] & 0x0F
        return frame.data[1:1 + length] if length and len(frame.data) >= length + 1 else None
    if pci_type == 0x1 and len(frame.data) >= 3:
        return frame.data[2:]
    return None


def _functional_steps(bundle: TraceBundle, start_index: int) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for frame in sorted(bundle.frames, key=lambda item: (item.ts_seconds, item.line_no)):
        annotation = bundle.frame_annotations.get(frame.frame_ref)
        if annotation is None or annotation.addressing_mode != "functional":
            continue
        payload = _functional_payload(frame)
        if payload is None:
            continue
        message = decode_uds(payload)
        steps.append(
            {
                "step_index": start_index + len(steps),
                "ts_start": frame.ts_seconds,
                "ts_end": frame.ts_seconds,
                "direction": "functional",
                "addressing": "functional",
                "pair_key": None,
                "sid": message.sid,
                "service_name": message.service_name,
                "subfunction": message.subfunction,
                "did": message.did,
                "block_seq": message.block_seq,
                "status_key": "functional",
                "request_raw": _message_detail(message)["raw"],
                "response_raw": None,
                "detail": _step_detail(message, None),
                "fields": _message_detail(message),
                "evidence_frame_refs": (frame.frame_ref,),
                "session": None,
            }
        )
    return steps


def build_workflow_steps(bundle: TraceBundle, cfg: AppConfig) -> list[dict[str, Any]]:
    """Build one readable step per UDS request plus functional requests."""

    steps: list[dict[str, Any]] = []
    for conversation in bundle.conversations:
        match = match_conversation(
            conversation,
            timing=cfg.timeouts,
            trace_end_ts=bundle.quality.end_ts,
        )
        for transaction in sorted(
            match.transactions,
            key=lambda item: item.pdu_req.ts_start if item.pdu_req is not None else 0.0,
        ):
            steps.append(_transaction_step(transaction, len(steps) + 1, conversation.pair_key))
    steps.extend(_functional_steps(bundle, len(steps) + 1))
    steps.sort(key=lambda item: (item["ts_start"], item["step_index"]))
    for index, step in enumerate(steps, start=1):
        step["step_index"] = index
    return steps


__all__ = ["build_workflow_steps"]
