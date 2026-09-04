"""Build and smoke-test the M7 PyInstaller onedir candidate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, timeout: int = 900) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _directory_stats(path: Path) -> tuple[int, int]:
    files = [item for item in path.rglob("*") if item.is_file()]
    return len(files), sum(item.stat().st_size for item in files)


def _smoke(executable: Path, seconds: float = 5.0) -> dict[str, Any]:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    started = time.perf_counter()
    process = subprocess.Popen([str(executable)], cwd=executable.parent, env=env)
    time.sleep(seconds)
    alive = process.poll() is None
    if alive:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    return {
        "status": "SUCCESS" if alive else "FAILED",
        "startup_ms": round((time.perf_counter() - started) * 1000, 2),
        "alive_after_window": alive,
        "returncode": process.returncode,
    }


def build(output_path: Path) -> dict[str, Any]:
    dist_path = ROOT / "dist" / "m7_pyinstaller"
    work_path = ROOT / "build" / "m7_pyinstaller"
    spec_path = ROOT / "build" / "m7_pyinstaller"
    if dist_path.exists():
        shutil.rmtree(dist_path)
    if work_path.exists():
        shutil.rmtree(work_path)
    assets = ROOT / "src" / "flashreport_gui" / "assets"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "FlashReport",
        "--paths",
        str(ROOT / "src"),
        "--add-data",
        f"{assets};flashreport_gui/assets",
        "--workpath",
        str(work_path),
        "--distpath",
        str(dist_path),
        "--specpath",
        str(spec_path),
        str(ROOT / "tools" / "packaging_gui_entry.py"),
    ]
    build_result = _run(command)
    executable = dist_path / "FlashReport" / "FlashReport.exe"
    package_files = package_bytes = 0
    if executable.is_file():
        package_files, package_bytes = _directory_stats(executable.parent)
    smoke = _smoke(executable) if executable.is_file() else {"status": "SKIPPED_NO_EXE"}
    preflight_path = ROOT / "artifacts" / "M7-deploy-preflight.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8")) if preflight_path.is_file() else {}
    result = {
        "route_a": {
            "tool": "PyInstaller onedir",
            "build": "SUCCESS" if build_result["returncode"] == 0 and executable.is_file() else "FAILED",
            "dist": str(executable.parent) if executable.is_file() else None,
            "dist_mb": round(package_bytes / 1_048_576, 3),
            "file_count": package_files,
            "build_elapsed_ms": build_result["elapsed_ms"],
            "startup": smoke,
            "log": build_result,
        },
        "route_b": {
            "tool": "pyside6-deploy",
            "build": "SKIPPED_ENVIRONMENT" if preflight.get("decision") != "RUN_B" else "NOT_RUN",
            "reason": "pyside6-deploy/MSVC environment unavailable; route A remains authoritative",
        },
        "private_corpus_included": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build M7 candidate / 构建 M7 发布候选包")
    parser.add_argument("--output", type=Path, default=Path("artifacts/M7-build-benchmark.json"))
    args = parser.parse_args(argv)
    result = build(args.output)
    print(json.dumps({"route_a": result["route_a"]["build"], "startup": result["route_a"]["startup"]["status"]}, ensure_ascii=False))
    return 0 if result["route_a"]["build"] == "SUCCESS" and result["route_a"]["startup"]["status"] == "SUCCESS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
