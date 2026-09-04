from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..models import RawFrame


class ReaderError(RuntimeError):
    """Raised when an input trace cannot be read by the selected reader."""


@dataclass
class ReaderResult:
    """Frames plus input diagnostics produced by an M1 reader."""

    frames: list[RawFrame]
    input_stats: dict[str, Any]

    def __iter__(self):
        yield self.frames
        yield self.input_stats

    def __len__(self) -> int:
        return len(self.frames)


def normalize_channel(value: Any) -> int | str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace") or None
    text = str(value).strip()
    if not text:
        return None
    if text.isdecimal():
        return int(text)
    return text


def frame_from_message(message: Any, source: str, sequence: int) -> RawFrame:
    timestamp = getattr(message, "timestamp", None)
    can_id = getattr(message, "arbitration_id", getattr(message, "can_id", None))
    if timestamp is None or can_id is None:
        raise ValueError("object does not expose timestamp and arbitration_id")

    timestamp = float(timestamp)
    can_id = int(can_id)
    data = bytes(getattr(message, "data", b""))
    dlc = int(getattr(message, "dlc", len(data)))
    is_extended = bool(
        getattr(
            message,
            "is_extended_id",
            getattr(message, "is_extended", can_id > 0x7FF),
        )
    )
    metadata = {
        "reader": source,
        "message_type": type(message).__name__,
        "timestamp": timestamp,
    }
    return RawFrame(
        ts_seconds=timestamp,
        ts_display=f"{timestamp:.6f}",
        source_ts_metadata=metadata,
        can_id=can_id,
        is_extended=is_extended,
        channel=normalize_channel(getattr(message, "channel", None)),
        is_fd=bool(getattr(message, "is_fd", False)),
        dlc=dlc,
        data=data,
        source=source,
        line_no=sequence,
        is_remote_frame=bool(getattr(message, "is_remote_frame", False)),
        is_error_frame=bool(getattr(message, "is_error_frame", False)),
    )


def result_from_messages(messages: Iterable[Any], source: str) -> ReaderResult:
    frames: list[RawFrame] = []
    skipped_objects = 0
    for sequence, message in enumerate(messages, start=1):
        try:
            if isinstance(message, RawFrame):
                frames.append(message)
            else:
                frames.append(frame_from_message(message, source, sequence))
        except (TypeError, ValueError, AttributeError):
            skipped_objects += 1

    frames.sort(key=lambda frame: frame.ts_seconds)
    unknown_channel_count = sum(frame.channel is None for frame in frames)
    warnings: list[str] = []
    if unknown_channel_count:
        warnings.append("unknown_channel")
    if skipped_objects:
        warnings.append("unknown_objects_skipped")
    input_stats = {
        "source": source,
        "reader": source,
        "frame_count": len(frames),
        "unknown_channel_count": unknown_channel_count,
        "skipped_object_count": skipped_objects,
        "is_fd_count": sum(frame.is_fd for frame in frames),
        "remote_frame_count": sum(frame.is_remote_frame for frame in frames),
        "error_frame_count": sum(frame.is_error_frame for frame in frames),
        "warnings": warnings,
        "time_monotonic": all(
            left.ts_seconds <= right.ts_seconds
            for left, right in zip(frames, frames[1:])
        ),
    }
    return ReaderResult(frames=frames, input_stats=input_stats)


def read_trace(path: str | Path) -> ReaderResult:
    trace_path = Path(path)
    suffix = trace_path.suffix.lower()
    if suffix == ".asc":
        from .asc import read_asc

        return read_asc(trace_path)
    if suffix == ".blf":
        from .blf import read_blf

        return read_blf(trace_path)
    raise ReaderError(f"unsupported trace extension: {trace_path.suffix or '<none>'}")


load_frames = read_trace
