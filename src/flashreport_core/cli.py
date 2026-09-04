from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


def count_input_records(path: Path) -> int:
    """Count candidate records for the M0 CLI smoke test.

    Full ASC/BLF decoding belongs to M1. M0 deliberately keeps this fallback
    format-agnostic and only counts non-empty, non-comment text records.
    """
    headers = ("date ", "base ", "version ", "internal events logged")
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(
            1
            for line in handle
            if line.strip()
            and not line.lstrip().startswith((";", "#", "//"))
            and not line.lstrip().lower().startswith(headers)
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flashreport")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser("analyze", help="analyze an ASC or BLF trace")
    analyze.add_argument("file", type=Path)
    analyze.add_argument("--config", type=Path)
    analyze.add_argument("--out", choices=("md", "json"), default="md")
    analyze.add_argument("--out-json", type=Path)
    analyze.add_argument("--spec", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "analyze":
        return 2
    if not args.file.is_file():
        print(f"ERROR: input file not found: {args.file}")
        return 2
    try:
        frame_count = count_input_records(args.file)
    except OSError as exc:
        print(f"ERROR: cannot read input file: {exc}")
        return 2
    print("FLASHREPORT M0 CLI")
    print(f"SOURCE : {args.file}")
    print(f"FRAMES : {frame_count}")
    print("STATUS : skeleton; full analysis starts in M1-M5")
    return 0 if frame_count > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
