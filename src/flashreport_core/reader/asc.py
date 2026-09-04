from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

try:
    import can
except ImportError:  # pragma: no cover - exercised only in dependency-free installs
    can = None

from ..models import RawFrame
from .base import ReaderError, ReaderResult, normalize_channel, result_from_messages


_CANDUMP_RE = re.compile(
    r"^\s*\((?P<ts>[0-9]+(?:\.[0-9]+)?)\)\s+"
    r"(?:(?P<channel>[^\s]+)\s+)?"
    r"(?P<can_id>[0-9A-Fa-f]+)(?P<separator>##|#)(?P<data>[0-9A-Fa-f]*)\s*$"
)


def _parse_hex_id(token: str) -> tuple[int, bool]:
    clean = token.strip().rstrip("xX")
    if clean.lower().startswith("0x"):
        clean = clean[2:]
    if not clean:
        raise ValueError("empty CAN ID")
    return int(clean, 16), token.lower().endswith("x") or len(clean) > 3


def _parse_data_tokens(tokens: list[str], start: int, dlc: int) -> bytes:
    values: list[int] = []
    for token in tokens[start:]:
        clean = token.strip().rstrip(",")
        if not re.fullmatch(r"[0-9A-Fa-f]{2}", clean):
            continue
        values.append(int(clean, 16))
        if len(values) == dlc:
            break
    if len(values) < dlc:
        raise ValueError(f"record contains {len(values)} data bytes, expected {dlc}")
    return bytes(values)


def _raw_frame(
    *,
    timestamp: float,
    channel: int | str | None,
    can_id: int,
    is_extended: bool,
    is_fd: bool,
    dlc: int,
    data: bytes,
    line_no: int,
    is_remote_frame: bool = False,
    is_error_frame: bool = False,
) -> RawFrame:
    return RawFrame(
        ts_seconds=timestamp,
        ts_display=f"{timestamp:.6f}",
        source_ts_metadata={"reader": "asc-fallback", "line": line_no},
        can_id=can_id,
        is_extended=is_extended,
        channel=channel,
        is_fd=is_fd,
        dlc=dlc,
        data=data,
        source="asc",
        line_no=line_no,
        is_remote_frame=is_remote_frame,
        is_error_frame=is_error_frame,
    )


def _parse_candump_line(line: str, line_no: int) -> RawFrame | None:
    match = _CANDUMP_RE.match(line)
    if not match:
        return None
    can_id, is_extended = _parse_hex_id(match.group("can_id"))
    data_text = match.group("data")
    if len(data_text) % 2:
        raise ValueError("candump data has an odd number of hex digits")
    data = bytes.fromhex(data_text)
    return _raw_frame(
        timestamp=float(match.group("ts")),
        channel=normalize_channel(match.group("channel")),
        can_id=can_id,
        is_extended=is_extended,
        is_fd=match.group("separator") == "##",
        dlc=len(data),
        data=data,
        line_no=line_no,
        is_remote_frame=not bool(data_text),
    )


def _parse_vector_line(line: str, line_no: int) -> RawFrame | None:
    tokens = line.split()
    if len(tokens) < 5:
        return None
    try:
        timestamp = float(tokens[0])
    except ValueError:
        return None

    if len(tokens) >= 4 and tokens[3].lower() in {"rx", "tx"}:
        channel_token = tokens[1]
        can_token = tokens[2]
        remainder_start = 4
    elif len(tokens) >= 3 and tokens[2].lower() in {"rx", "tx"}:
        channel_token = None
        can_token = tokens[1]
        remainder_start = 3
    else:
        return None

    can_id, is_extended = _parse_hex_id(can_token)
    remainder = tokens[remainder_start:]
    marker_index = next(
        (index for index, token in enumerate(remainder) if token.lower() in {"d", "r", "d8", "d64"}),
        None,
    )
    if marker_index is None:
        return None
    marker = remainder[marker_index].lower()
    is_remote_frame = marker == "r"
    explicit_fd = marker == "d64" or any(
        token.lower() in {"fd", "canfd"} for token in remainder
    )
    after_marker = remainder[marker_index + 1 :]
    if marker in {"d8", "d64"}:
        dlc = int(marker[1:])
        data_start = 0
    elif after_marker and after_marker[0].isdigit():
        dlc = int(after_marker[0])
        data_start = 1
    else:
        dlc = 0 if is_remote_frame else len(after_marker)
        data_start = 0
    data = b"" if is_remote_frame else _parse_data_tokens(after_marker, data_start, dlc)
    return _raw_frame(
        timestamp=timestamp,
        channel=normalize_channel(channel_token),
        can_id=can_id,
        is_extended=is_extended,
        is_fd=explicit_fd,
        dlc=dlc,
        data=data,
        line_no=line_no,
        is_remote_frame=is_remote_frame,
        is_error_frame=any(token.lower() in {"error", "errorframe"} for token in tokens),
    )


def parse_asc_lines(lines: Iterable[str]) -> ReaderResult:
    frames: list[RawFrame] = []
    skipped_objects = 0
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith((";", "#", "//")):
            continue
        try:
            frame = _parse_candump_line(stripped, line_no)
            if frame is None:
                frame = _parse_vector_line(stripped, line_no)
            if frame is None:
                continue
            frames.append(frame)
        except (TypeError, ValueError):
            skipped_objects += 1

    result = result_from_messages(frames, "asc")
    result.input_stats["reader"] = "asc-fallback"
    result.input_stats["skipped_object_count"] += skipped_objects
    if skipped_objects and "unknown_objects_skipped" not in result.input_stats["warnings"]:
        result.input_stats["warnings"].append("unknown_objects_skipped")
    return result


def _read_native(path: Path) -> ReaderResult:
    if can is None:
        raise ReaderError("python-can is not installed")
    return result_from_messages(can.ASCReader(str(path)), "asc")


def read_asc(path: str | Path, *, prefer_native: bool = True) -> ReaderResult:
    trace_path = Path(path)
    if not trace_path.is_file():
        raise FileNotFoundError(trace_path)
    if prefer_native:
        try:
            native_result = _read_native(trace_path)
            # ASCReader compatibility varies by header and dialect. Compare
            # with the controlled text fallback so a partial native parse is
            # never accepted silently.
            with trace_path.open("r", encoding="utf-8", errors="replace") as handle:
                fallback_result = parse_asc_lines(handle)
            if fallback_result.input_stats["frame_count"] > native_result.input_stats["frame_count"]:
                return fallback_result
            return native_result
        except Exception:
            pass
    try:
        with trace_path.open("r", encoding="utf-8", errors="replace") as handle:
            return parse_asc_lines(handle)
    except OSError as exc:
        raise ReaderError(f"cannot read ASC trace: {trace_path}") from exc


read_asc_frames = read_asc
