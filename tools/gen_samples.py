from __future__ import annotations

import json
from pathlib import Path


SCENARIOS = [
    ("success_full_download", "implemented"),
    ("success_bs0_no_extra_fc", "planned"),
    ("ecu_no_fc_after_ff", "planned"),
    ("ecu_no_fc_after_block", "implemented"),
    ("tester_no_next_block", "implemented"),
    ("tester_sn_error", "planned"),
    ("tester_stmin_violation", "planned"),
    ("ecu_no_final_after_36", "planned"),
    ("ecu_pending_then_success", "planned"),
    ("flash_oversize_block", "implemented"),
    ("flash_oversize_boundary_ok", "planned"),
    ("tester_wrong_bsc", "planned"),
    ("security_access_skipped", "implemented"),
    ("missing_fc_cf_complete", "planned"),
    ("multi_channel_same_ids", "planned"),
    ("interleaved_request_ambiguous", "planned"),
]

IMPLEMENTED = {name for name, status in SCENARIOS if status == "implemented"}


def _asc_line(ts: float, can_id: str, data: list[int]) -> str:
    payload = " ".join(f"{value:02X}" for value in data)
    padded = " ".join(f"{value:02X}" for value in data + [0] * (8 - len(data)))
    return f"{ts:0.6f} 1 {can_id}x Rx d 8 {padded}"


def generate_samples(root: Path) -> list[str]:
    samples = root / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []
    for name, status in SCENARIOS:
        if name not in IMPLEMENTED:
            continue
        frames = [
            _asc_line(0.000000, "18DA10F1", [0x02, 0x10, 0x02]),
            _asc_line(0.002000, "18DAF110", [0x02, 0x50, 0x02]),
        ]
        if name == "ecu_no_fc_after_block":
            frames.append(_asc_line(0.004000, "18DA10F1", [0x10, 0x14, 0x36, 0x17, 0, 0, 0, 0]))
        elif name == "tester_no_next_block":
            frames.append(_asc_line(0.004000, "18DA10F1", [0x10, 0x14, 0x36, 0x17, 0, 0, 0, 0]))
            frames.append(_asc_line(0.006000, "18DAF110", [0x30, 0x08, 0x05]))
        elif name == "flash_oversize_block":
            frames.append(_asc_line(0.004000, "18DAF110", [0x04, 0x74, 0x40, 0x02]))
            frames.append(_asc_line(0.006000, "18DA10F1", [0x10, 0x06, 0x36, 0x17, 1, 2, 3, 4]))
        elif name == "security_access_skipped":
            frames.append(_asc_line(0.004000, "18DA10F1", [0x02, 0x34, 0x00]))
            frames.append(_asc_line(0.006000, "18DAF110", [0x03, 0x7F, 0x27, 0x33]))
        generated.append(name)
        (samples / f"{name}.asc").write_text(
            "date Thu Jan 01 00:00:00.000 1970\n"
            "base hex  timestamps absolute\n"
            + "\n".join(frames)
            + "\n",
            encoding="ascii",
        )
        expected = {
            "schema_version": "m0",
            "scenario": name,
            "status": status,
            "findings": [],
            "first_deviation": None,
            "ambiguous": False,
        }
        (samples / f"{name}.expected.json").write_text(
            json.dumps(expected, indent=2) + "\n",
            encoding="utf-8",
        )
    return generated


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    assert len(SCENARIOS) == 16, "M0 scenario registry must contain exactly 16 entries"
    generated = generate_samples(root)
    print(f"registered_scenarios={len(SCENARIOS)}")
    print(f"generated_scenarios={len(generated)}")
    print("generated=" + ",".join(generated))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

