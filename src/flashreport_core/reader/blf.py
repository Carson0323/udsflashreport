from __future__ import annotations

from pathlib import Path

try:
    import can
except ImportError:  # pragma: no cover - exercised only in dependency-free installs
    can = None

from .base import ReaderError, ReaderResult, result_from_messages


def read_blf(path: str | Path) -> ReaderResult:
    trace_path = Path(path)
    if not trace_path.is_file():
        raise FileNotFoundError(trace_path)
    if can is None:
        raise ReaderError("python-can is not installed")
    try:
        return result_from_messages(can.BLFReader(str(trace_path)), "blf")
    except Exception as exc:
        raise ReaderError(f"cannot read BLF trace: {trace_path}") from exc


read_blf_frames = read_blf
