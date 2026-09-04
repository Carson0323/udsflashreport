from __future__ import annotations

"""Small M3 oracle comparison for UDS fields supported by the project."""

import argparse
import json
from pathlib import Path

from flashreport_core.uds.decoder import decode_uds, extract_server_timing


CASES = {
    "diagnostic_session_timing": bytes.fromhex("5002003201F4"),
    "request_download_max_0x402": bytes.fromhex("74200402"),
    "transfer_data_response_bsc": bytes.fromhex("7617"),
}


def _ours(payload: bytes) -> dict:
    message = decode_uds(payload)
    timing = extract_server_timing(payload)
    return {
        "sid": message.sid,
        "service_name": message.service_name,
        "block_seq": message.block_seq,
        "max_block_length": message.max_block_length,
        "p2_ms": timing.p2_ms if timing else None,
        "p2_star_ms": timing.p2_star_ms if timing else None,
    }


def _udsoncan(payload: bytes) -> dict:
    from udsoncan.Response import Response
    from udsoncan.services.DiagnosticSessionControl import DiagnosticSessionControl
    from udsoncan.services.RequestDownload import RequestDownload

    result = {
        "sid": payload[0] if payload else None,
        "service_name": None,
        "block_seq": payload[1] if payload and payload[0] == 0x76 and len(payload) > 1 else None,
        "max_block_length": None,
        "p2_ms": None,
        "p2_star_ms": None,
    }
    if payload[:1] == b"\x50":
        interpreted = DiagnosticSessionControl.interpret_response(Response.from_payload(payload))
        result["service_name"] = "DiagnosticSessionControl"
        result["p2_ms"] = round(interpreted.service_data.p2_server_max * 1000)
        result["p2_star_ms"] = round(interpreted.service_data.p2_star_server_max * 1000)
    elif payload[:1] == b"\x74":
        interpreted = RequestDownload.interpret_response(Response.from_payload(payload))
        result["service_name"] = "RequestDownload"
        result["max_block_length"] = interpreted.service_data.max_length
    elif payload[:1] == b"\x76":
        result["service_name"] = "TransferData"
    return result


def build_report() -> dict:
    try:
        import udsoncan  # noqa: F401
    except ImportError:
        return {
            "status": "BLOCKED_ORACLE_NOT_INSTALLED",
            "cases": {},
            "note": "Install udsoncan in the project environment to execute the M3 oracle comparison.",
        }

    cases = {}
    for name, payload in CASES.items():
        ours = _ours(payload)
        oracle = _udsoncan(payload)
        cases[name] = {
            "payload": payload.hex().upper(),
            "ours": ours,
            "udsoncan": oracle,
            "match": ours == oracle,
        }
    return {
        "status": "PASS" if all(case["match"] for case in cases.values()) else "DIFF_REQUIRES_REVIEW",
        "oracle": "udsoncan",
        "oracle_version": "1.26.1",
        "cases": cases,
        "note": "Oracle comparison is a decoder cross-check, not attribution ground truth. / 对拍仅验证解码字段，不是归因 ground truth。",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/M3-oracle-diff.json"))
    args = parser.parse_args()
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
