"""Generate local-only fault-injection variants for a private trace corpus.

The tool contains no project data. It accepts a user-selected local directory,
keeps the originals untouched, and writes all generated variants to a new
output directory. / 本工具不包含项目数据，只处理用户指定的本机目录，保留原始
记录不变，并把生成的变体写入新目录。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

import can


SCENARIOS = (
    "cut_after_stage_timeout",
    "missing_flow_control_timeout",
    "ecu_negative_response",
    "cf_sequence_violation",
)
REQUEST_SERVICES = {0x10, 0x11, 0x27, 0x28, 0x2E, 0x31, 0x34, 0x36, 0x37}
STAGE_SERVICES = (0x36, 0x34, 0x37, 0x31, 0x27, 0x10)


@dataclass
class TraceRecord:
    timestamp: float
    can_id: int
    data: bytes
    channel: int | str | None
    is_extended: bool
    is_fd: bool
    direction: str = ""
    row: list[str] | None = None
    is_remote_frame: bool = False
    is_error_frame: bool = False


@dataclass
class CsvSchema:
    preamble: list[str]
    header: list[str]
    sequence: int
    can_id: int
    length: int
    data: int
    timestamp: int
    direction: int
    frame_type: int
    frame_format: int
    can_type: int
    channel: int
    device: int


@dataclass
class SourceTrace:
    path: Path
    records: list[TraceRecord]
    format: str
    csv_schema: CsvSchema | None = None


@dataclass
class InjectionResult:
    records: list[TraceRecord]
    status: str
    target: dict[str, Any] = field(default_factory=dict)
    operation: dict[str, Any] = field(default_factory=dict)


def _iso_tp_kind(data: bytes) -> str | None:
    if not data:
        return None
    return {
        0x0: "sf",
        0x1: "ff",
        0x2: "cf",
        0x3: "fc",
    }.get(data[0] >> 4)


def _uds_payload(data: bytes) -> bytes | None:
    kind = _iso_tp_kind(data)
    if kind == "sf":
        length = data[0] & 0x0F
        return data[1 : 1 + length]
    if kind == "ff" and len(data) >= 2:
        return data[2:]
    return None


def _uds_service(data: bytes) -> int | None:
    payload = _uds_payload(data)
    if not payload:
        return None
    if payload[0] == 0x7F and len(payload) >= 2:
        return payload[1]
    return payload[0]


def _is_request(data: bytes) -> bool:
    payload = _uds_payload(data)
    service = _uds_service(data)
    return bool(
        payload
        and payload[0] != 0x7F
        and service in REQUEST_SERVICES
        and service < 0x40
    )


def _same_channel(left: TraceRecord, right: TraceRecord) -> bool:
    return left.channel == right.channel


def _clone_records(records: Iterable[TraceRecord]) -> list[TraceRecord]:
    return [replace(record, data=bytes(record.data), row=list(record.row) if record.row else None) for record in records]


def _target_details(record: TraceRecord, index: int) -> dict[str, Any]:
    return {
        "record_index": index + 1,
        "timestamp": record.timestamp,
        "can_id": f"0x{record.can_id:X}",
        "iso_tp_kind": _iso_tp_kind(record.data),
        "uds_service": _uds_service(record.data),
    }


def _find_stage_request(records: list[TraceRecord]) -> int | None:
    candidates = [
        index
        for index, record in enumerate(records)
        if _is_request(record.data) and _uds_service(record.data) in STAGE_SERVICES
    ]
    if not candidates:
        return None
    for service in STAGE_SERVICES:
        for index in candidates:
            if _uds_service(records[index].data) == service:
                return index
    return candidates[0]


def _find_flow_control(records: list[TraceRecord]) -> tuple[int, int] | None:
    candidates: list[tuple[int, int, int]] = []
    for ff_index, ff in enumerate(records):
        if _iso_tp_kind(ff.data) != "ff":
            continue
        total_len = ((ff.data[0] & 0x0F) << 8 | ff.data[1]) if len(ff.data) >= 2 else 0
        end = min(len(records), ff_index + 513)
        for fc_index in range(ff_index + 1, end):
            fc = records[fc_index]
            if (
                _iso_tp_kind(fc.data) == "fc"
                and _same_channel(ff, fc)
                and fc.can_id != ff.can_id
            ):
                candidates.append((total_len, ff_index, fc_index))
                break
    if not candidates:
        return None
    # Prefer a real transfer block over a short control PDU. Removing its
    # FC is then observable as a timeout rather than being masked by a later
    # FC belonging to the next short PDU.
    _, ff_index, fc_index = max(candidates, key=lambda item: (item[0], -item[1]))
    return ff_index, fc_index


def _find_cf_pair(records: list[TraceRecord]) -> tuple[int, int] | None:
    streams: dict[tuple[int | str | None, int], list[int]] = {}
    for index, record in enumerate(records):
        if _iso_tp_kind(record.data) == "cf":
            streams.setdefault((record.channel, record.can_id), []).append(index)
    for indexes in streams.values():
        for left_index, right_index in zip(indexes, indexes[1:]):
            left_sn = records[left_index].data[0] & 0x0F
            right_sn = records[right_index].data[0] & 0x0F
            if right_sn == ((left_sn + 1) & 0x0F):
                return left_index, right_index
    return None


def _find_response_id(records: list[TraceRecord], request_index: int) -> int | None:
    request = records[request_index]
    service = _uds_service(request.data)
    for record in records[request_index + 1 :]:
        if not _same_channel(request, record) or record.can_id == request.can_id:
            continue
        response_service = _uds_service(record.data)
        if response_service in {service + 0x40 if service is not None else -1, service}:
            return record.can_id
    for record in records:
        if _same_channel(request, record) and record.can_id != request.can_id:
            return record.can_id
    return None


def _find_negative_request(records: list[TraceRecord]) -> int | None:
    """Find a complete SF request suitable for an injected NRC response."""

    for service in (0x34, 0x36, 0x37, 0x31, 0x27, 0x10, 0x11):
        for index, record in enumerate(records):
            if (
                _iso_tp_kind(record.data) == "sf"
                and _is_request(record.data)
                and _uds_service(record.data) == service
            ):
                return index
    return next(
        (
            index
            for index, record in enumerate(records)
            if _iso_tp_kind(record.data) == "sf" and _is_request(record.data)
        ),
        None,
    )


def _negative_response(request: TraceRecord, response_id: int, service: int) -> TraceRecord:
    nrc = 0x72 if service in {0x34, 0x36, 0x37} else 0x13
    return TraceRecord(
        timestamp=request.timestamp + 0.0001,
        can_id=response_id,
        data=bytes([0x03, 0x7F, service, nrc, 0xFF, 0xFF, 0xFF, 0xFF]),
        channel=request.channel,
        is_extended=request.is_extended,
        is_fd=False,
        direction="接收",
    )


def inject(records: list[TraceRecord], scenario: str) -> InjectionResult:
    """Apply one deterministic fault injection without mutating the input."""

    if scenario == "cut_after_stage_timeout":
        index = _find_stage_request(records)
        if index is None:
            return InjectionResult(_clone_records(records), "SKIPPED_NO_STAGE", operation={"scenario": scenario})
        return InjectionResult(
            _clone_records(records[: index + 1]),
            "INJECTED",
            target=_target_details(records[index], index),
            operation={"scenario": scenario, "effect": "truncate_after_target_request"},
        )

    if scenario == "missing_flow_control_timeout":
        pair = _find_flow_control(records)
        if pair is None:
            return InjectionResult(_clone_records(records), "SKIPPED_NO_FLOW_CONTROL", operation={"scenario": scenario})
        ff_index, fc_index = pair
        ff = records[ff_index]
        removal_indexes = {
            index
            for index, record in enumerate(records)
            if (
                index > ff_index
                and record.timestamp <= ff.timestamp + 1.0
                and _iso_tp_kind(record.data) == "fc"
                and _same_channel(ff, record)
                and record.can_id != ff.can_id
            )
        }
        removal_indexes.add(fc_index)
        result = _clone_records(
            record for index, record in enumerate(records) if index not in removal_indexes
        )
        return InjectionResult(
            result,
            "INJECTED",
            target={
                "ff": _target_details(records[ff_index], ff_index),
                "removed_fc": _target_details(records[fc_index], fc_index),
                "removed_fc_count": len(removal_indexes),
            },
            operation={
                "scenario": scenario,
                "effect": "remove_fc_frames_for_one_second_after_ff",
                "removed_fc_count": len(removal_indexes),
            },
        )

    if scenario == "ecu_negative_response":
        index = _find_negative_request(records)
        if index is None:
            return InjectionResult(_clone_records(records), "SKIPPED_NO_REQUEST", operation={"scenario": scenario})
        service = _uds_service(records[index].data)
        response_id = _find_response_id(records, index)
        if service is None or response_id is None:
            return InjectionResult(_clone_records(records), "SKIPPED_NO_PAIR", operation={"scenario": scenario})
        result = _clone_records(records)
        result.insert(index + 1, _negative_response(records[index], response_id, service))
        result.sort(key=lambda record: record.timestamp)
        return InjectionResult(
            result,
            "INJECTED",
            target=_target_details(records[index], index),
            operation={
                "scenario": scenario,
                "effect": "insert_ecu_negative_response",
                "response_id": f"0x{response_id:X}",
                "nrc": "0x72" if service in {0x34, 0x36, 0x37} else "0x13",
            },
        )

    if scenario == "cf_sequence_violation":
        pair = _find_cf_pair(records)
        if pair is None:
            return InjectionResult(_clone_records(records), "SKIPPED_NO_CF_PAIR", operation={"scenario": scenario})
        left_index, right_index = pair
        result = _clone_records(records)
        left_data = result[left_index].data
        result[left_index] = replace(result[left_index], data=result[right_index].data)
        result[right_index] = replace(result[right_index], data=left_data)
        return InjectionResult(
            result,
            "INJECTED",
            target={
                "first_cf": _target_details(records[left_index], left_index),
                "second_cf": _target_details(records[right_index], right_index),
            },
            operation={"scenario": scenario, "effect": "swap_consecutive_cf_payloads"},
        )

    raise ValueError(f"unknown injection scenario: {scenario}")


def _parse_hex_bytes(value: str) -> bytes:
    return bytes(int(token, 16) for token in re.findall(r"[0-9A-Fa-f]{2}", value))


def _parse_csv_timestamp(value: str) -> float:
    value = value.strip()
    match = re.fullmatch(r"(\d+):(\d+):(\d+)(?:\.(\d+))?", value)
    if match:
        fraction = (match.group(4) or "0")[:6].ljust(6, "0")
        return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + int(match.group(3)) + int(fraction) / 1_000_000
    return float(value)


def _format_csv_timestamp(value: float) -> str:
    milliseconds = max(0, int(round(value * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _column(header: list[str], name: str, fallback: int) -> int:
    try:
        return header.index(name)
    except ValueError:
        return fallback


def _load_csv(path: Path) -> SourceTrace:
    raw = path.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(f"cannot decode CSV: {path}")
    lines = text.splitlines()
    rows = list(csv.reader(lines))
    header_index = next((i for i, row in enumerate(rows) if "帧ID(HEX)" in row), None)
    if header_index is None:
        raise ValueError(f"unsupported CSV header: {path}")
    header = rows[header_index]
    indexes = {
        "sequence": _column(header, "序号", 0),
        "can_id": _column(header, "帧ID(HEX)", 1),
        "length": _column(header, "长度", 2),
        "data": _column(header, "数据(HEX)", 3),
        "timestamp": _column(header, "时间标识", 4),
        "direction": _column(header, "方向", 5),
        "frame_type": _column(header, "帧类型", 6),
        "frame_format": _column(header, "帧格式", 7),
        "can_type": _column(header, "CAN类型", 8),
        "channel": _column(header, "通道号", 9),
        "device": _column(header, "设备号", 10),
    }
    schema = CsvSchema(
        preamble=lines[:header_index],
        header=header,
        **indexes,
    )
    records: list[TraceRecord] = []
    for row in rows[header_index + 1 :]:
        if len(row) <= max(indexes.values()) or not row[indexes["can_id"]].strip():
            continue
        data = _parse_hex_bytes(row[indexes["data"]])
        can_id_text = row[indexes["can_id"]].strip().lower().replace("0x", "")
        can_id = int(can_id_text, 16)
        channel = row[indexes["channel"]].strip() or None
        records.append(
            TraceRecord(
                timestamp=_parse_csv_timestamp(row[indexes["timestamp"]]),
                can_id=can_id,
                data=data,
                channel=channel,
                is_extended=can_id > 0x7FF,
                is_fd=False,
                direction=row[indexes["direction"]].strip(),
                row=list(row),
            )
        )
    records.sort(key=lambda record: record.timestamp)
    return SourceTrace(path=path, records=records, format="csv", csv_schema=schema)


def _load_blf(path: Path) -> SourceTrace:
    records: list[TraceRecord] = []
    for message in can.BLFReader(str(path)):
        records.append(
            TraceRecord(
                timestamp=float(message.timestamp),
                can_id=int(message.arbitration_id),
                data=bytes(message.data),
                channel=getattr(message, "channel", None),
                is_extended=bool(message.is_extended_id),
                is_fd=bool(message.is_fd),
                is_remote_frame=bool(message.is_remote_frame),
                is_error_frame=bool(message.is_error_frame),
            )
        )
    records.sort(key=lambda record: record.timestamp)
    return SourceTrace(path=path, records=records, format="blf")


def load_source(path: Path) -> SourceTrace:
    if path.suffix.lower() == ".csv":
        return _load_csv(path)
    if path.suffix.lower() == ".blf":
        return _load_blf(path)
    raise ValueError(f"unsupported private trace format: {path.suffix}")


def _row_for_record(record: TraceRecord, schema: CsvSchema, sequence: int, template: list[str]) -> list[str]:
    row = list(record.row) if record.row is not None else list(template)
    if len(row) < len(schema.header):
        row.extend([""] * (len(schema.header) - len(row)))
    row[schema.sequence] = str(sequence)
    row[schema.can_id] = f"0x{record.can_id:X}"
    row[schema.length] = str(len(record.data))
    row[schema.data] = " ".join(f"{value:02X}" for value in record.data)
    row[schema.timestamp] = _format_csv_timestamp(record.timestamp)
    if record.direction:
        row[schema.direction] = record.direction
    return row


def _write_csv(path: Path, source: SourceTrace, records: list[TraceRecord]) -> None:
    assert source.csv_schema is not None
    schema = source.csv_schema
    template = next((record.row for record in source.records if record.row), [""] * len(schema.header))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if schema.preamble:
            handle.write("\n".join(schema.preamble) + "\n")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(schema.header)
        for sequence, record in enumerate(records, start=1):
            writer.writerow(_row_for_record(record, schema, sequence, template))


def _write_asc(path: Path, records: list[TraceRecord]) -> None:
    base = records[0].timestamp if records else 0.0
    previous_timestamp = -1.0
    with path.open("w", encoding="ascii", newline="\n") as handle:
        handle.write("; Generated local-only analysis view\n")
        for record in records:
            timestamp = max(0.0, record.timestamp - base)
            # CSV captures only millisecond precision. Keep the original row
            # order deterministic by adding a microsecond tie-breaker in the
            # analysis companion, so FC-before-CF and CF sequence tests remain
            # observable without changing the source CSV.
            if timestamp <= previous_timestamp:
                timestamp = previous_timestamp + 0.000001
            previous_timestamp = timestamp
            channel = str(record.channel or "CAN1")
            separator = "##" if record.is_fd else "#"
            handle.write(
                f"({timestamp:.6f}) {channel} {record.can_id:X}{separator}{record.data.hex().upper()}\n"
            )


def _write_blf(path: Path, records: list[TraceRecord]) -> None:
    with can.BLFWriter(str(path)) as writer:
        for record in records:
            writer.on_message_received(
                can.Message(
                    timestamp=record.timestamp,
                    arbitration_id=record.can_id,
                    is_extended_id=record.is_extended,
                    is_fd=record.is_fd,
                    data=record.data,
                    channel=record.channel,
                    is_remote_frame=record.is_remote_frame,
                    is_error_frame=record.is_error_frame,
                )
            )


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return slug[:48] or "trace"


def generate(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    sources = sorted([*input_dir.glob("*.blf"), *input_dir.glob("*.csv")], key=lambda path: path.name)
    if not sources:
        raise FileNotFoundError(f"no .blf or .csv files in {input_dir}")
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing directory: {output_dir}")
    output_dir.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "purpose": "local-only fault injection / 仅本机错误注入",
        "source_directory": str(input_dir),
        "originals_modified": False,
        "network_upload": False,
        "scenarios": list(SCENARIOS),
        "sources": [],
    }
    for source_number, source_path in enumerate(sources, start=1):
        source = load_source(source_path)
        source_dir = output_dir / f"source_{source_number:02d}_{_safe_slug(source_path.stem)}"
        source_dir.mkdir()
        source_entry: dict[str, Any] = {
            "source_name": source_path.name,
            "source_format": source.format,
            "source_frame_count": len(source.records),
            "variants": [],
        }
        for scenario in SCENARIOS:
            injected = inject(source.records, scenario)
            suffix = ".csv" if source.format == "csv" else ".blf"
            output_path = source_dir / f"{source_number:02d}_{scenario}{suffix}"
            if source.format == "csv":
                _write_csv(output_path, source, injected.records)
                analysis_path = output_path.with_suffix(".analysis.asc")
                _write_asc(analysis_path, injected.records)
            else:
                _write_blf(output_path, injected.records)
                analysis_path = output_path
            source_entry["variants"].append(
                {
                    "scenario": scenario,
                    "status": injected.status,
                    "output": str(output_path),
                    "analysis_input": str(analysis_path),
                    "frame_count": len(injected.records),
                    "target": injected.target,
                    "operation": injected.operation,
                }
            )
        manifest["sources"].append(source_entry)
    manifest["summary"] = {
        "source_count": len(manifest["sources"]),
        "variant_count": sum(len(source["variants"]) for source in manifest["sources"]),
        "injected_count": sum(
            variant["status"] == "INJECTED"
            for source in manifest["sources"]
            for variant in source["variants"]
        ),
        "skipped_count": sum(
            variant["status"] != "INJECTED"
            for source in manifest["sources"]
            for variant in source["variants"]
        ),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        "# 本机错误注入语料 | Local fault-injection corpus\n\n"
        "此目录由 `tools/inject_private_corpus.py` 生成，仅用于本机验证。\n"
        "This directory was generated for local verification only.\n\n"
        "原始报文保留在上一级目录，未被修改；本目录不得复制到 Git 仓库或上传网络。\n"
        "Original traces remain untouched in the parent directory; do not commit or upload this directory.\n\n"
        "场景：流程切断后超时、缺失 FC 后超时、ECU 负响应、CF 序号异常。\n"
        "Scenarios: cut-flow timeout, missing-FC timeout, ECU negative response, and CF sequence violation.\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate local-only trace fault injections / 生成本机错误注入报文")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(argv)
    manifest = generate(args.input_dir, args.output_dir)
    print(json.dumps(manifest["summary"], ensure_ascii=False, sort_keys=True))
    return 0 if manifest["summary"]["skipped_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
