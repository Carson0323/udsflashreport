from __future__ import annotations

import json

from flashreport_core.cli import main


def test_cli_analyze_writes_markdown_and_json(tmp_path, capsys) -> None:
    md_path = tmp_path / "cli-report.md"
    json_path = tmp_path / "cli-report.json"
    code = main(
        [
            "analyze",
            "samples/success_full_download.asc",
            "--out",
            str(md_path),
            "--out-json",
            str(json_path),
        ]
    )
    output = capsys.readouterr().out
    assert code == 0
    assert "NO FINDINGS" in output
    assert md_path.is_file()
    assert json.loads(json_path.read_text(encoding="utf-8"))["findings"] == []


def test_cli_missing_input_returns_parse_error(capsys) -> None:
    code = main(["analyze", "does-not-exist.asc"])
    assert code == 2
    assert "not found" in capsys.readouterr().out


def test_cli_invalid_config_returns_config_error(tmp_path, capsys) -> None:
    config_path = tmp_path / "invalid.json"
    config_path.write_text(json.dumps({"unexpected": True}), encoding="utf-8")
    code = main(
        [
            "analyze",
            "samples/success_full_download.asc",
            "--config",
            str(config_path),
        ]
    )
    assert code == 3
    assert "configuration" in capsys.readouterr().out
