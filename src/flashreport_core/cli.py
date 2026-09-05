from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .api import analyze_trace, default_config, export_report, load_trace
from .attribution.engine import analyze_bundle
from .config import load_config
from .reader import ReaderError
from .rules.registry import load_rule_specs

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
    analyze.add_argument("--out", type=Path, help="Markdown output path")
    analyze.add_argument("--out-json", type=Path)
    analyze.add_argument("--spec", type=Path)
    return parser


def _print_result(result) -> None:
    first = result.first_deviation
    if first is None:
        print("STATUS         : NO FINDINGS")
        print("FIRST DEVIATION: none")
    else:
        print(f"FAILURE DOMAIN : {first.layer}")
        print(f"FIRST DEVIATION: {first.finding_id} {first.observed}")
        print(f"SESSION        : {first.session or 'unknown'}")
        print(f"UDS SERVICE    : {first.service or 'unknown'}")
        print(f"SUSPECTED SIDE : {first.suspected_side.upper()}")
        print(f"CONFIDENCE     : {first.confidence.upper()}")
        print(f"FINDINGS       : {len(result.findings)}")
    stats = result.report_data.get("input_stats", {})
    for warning in stats.get("warnings", []):
        print(f"INPUT WARNING  : {warning}")
    if stats.get("skipped_object_count"):
        print(f"INPUT QUALITY  : known incomplete; {stats['skipped_object_count']} records skipped")
    if not result.bundle.conversations:
        print("ANALYSIS SCOPE : no physical diagnostic conversation; check addressing and protocol support")
    if stats.get("ambiguous"):
        print("AMBIGUOUS      : review transaction pairing before relying on attribution")


def _output_paths(args) -> tuple[Path | None, Path | None]:
    md_path = args.out
    json_path = args.out_json
    if md_path is not None and md_path.suffix.lower() == ".json" and json_path is None:
        json_path = md_path
        md_path = None
    return md_path, json_path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "analyze":
        return 2
    if not args.file.is_file():
        print(f"ERROR: input file not found: {args.file}")
        return 2
    try:
        config = load_config(str(args.config)) if args.config is not None else default_config()
    except (OSError, ValueError) as exc:
        print(f"ERROR: invalid configuration: {exc}")
        return 3
    if args.spec is not None:
        spec_dir = args.spec if args.spec.is_dir() else args.spec.parent
        findings_path = spec_dir / "findings.yaml"
        try:
            load_rule_specs(findings_path)
        except (OSError, ValueError) as exc:
            print(f"ERROR: invalid spec registry: {exc}")
            return 3
    try:
        bundle = load_trace(str(args.file), config)
        if args.spec is None:
            result = analyze_trace(bundle, config)
        else:
            result = analyze_bundle(bundle, config, findings_path=str(findings_path))
    except (OSError, ReaderError, TypeError, ValueError) as exc:
        print(f"ERROR: cannot analyze input: {exc}")
        return 2

    _print_result(result)
    md_path, json_path = _output_paths(args)
    if md_path is None and json_path is None:
        return 0
    try:
        export_report(result, str(md_path) if md_path is not None else None, str(json_path) if json_path is not None else None)
    except (OSError, ValueError) as exc:
        print(f"ERROR: report validation/export failed: {exc}")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
