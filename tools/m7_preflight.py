"""Record the local Windows deployment-tool preflight required by M7."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _where(command: str) -> dict[str, Any]:
    environment = os.environ.copy()
    script_dir = str(Path(sys.executable).resolve().parent)
    environment["PATH"] = script_dir + os.pathsep + environment.get("PATH", "")
    completed = subprocess.run(
        ["where.exe", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
    )
    paths = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return {"available": bool(paths), "paths": paths, "stderr": completed.stderr.strip()}


def _dry_run(path: str | None) -> dict[str, Any]:
    if not path:
        return {"status": "SKIPPED_NOT_FOUND"}
    completed = subprocess.run(
        [path, "--dry-run"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    return {
        "status": "SUCCESS" if completed.returncode == 0 else "FAILED",
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def collect() -> dict[str, Any]:
    pyside_file = None
    shiboken_file = None
    try:
        import PySide6
        import shiboken6

        pyside_file = PySide6.__file__
        shiboken_file = shiboken6.__file__
    except ImportError as exc:
        import_error = f"{type(exc).__name__}: {exc}"
    else:
        import_error = None
    dumpbin = _where("dumpbin")
    pyinstaller = _where("pyinstaller")
    pyside_deploy = _where("pyside6-deploy")
    msvc_environment = bool(os.environ.get("VCToolsInstallDir")) or dumpbin["available"]
    nuitka = shutil.which("nuitka") is not None
    pyside_path = pyside_deploy["paths"][0] if pyside_deploy["paths"] else None
    return {
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "where": _where("python"),
        },
        "PySide6_file": pyside_file,
        "shiboken6_file": shiboken_file,
        "import_error": import_error,
        "where": {
            "dumpbin": dumpbin,
            "pyinstaller": pyinstaller,
            "pyside6-deploy": pyside_deploy,
        },
        "pyside6_deploy_dry_run": _dry_run(pyside_path),
        "pyside6_deploy_environment": {
            "dumpbin_available": dumpbin["available"],
            "msvc_environment": msvc_environment,
            "nuitka_available": nuitka,
        },
        "decision": "RUN_B" if pyside_deploy["available"] and msvc_environment else "SKIPPED_ENVIRONMENT",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record M7 deployment preflight / 记录 M7 部署预检")
    parser.add_argument("--output", type=Path, default=Path("artifacts/M7-deploy-preflight.json"))
    args = parser.parse_args(argv)
    result = collect()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"decision": result["decision"], "python": result["python"]["version"].splitlines()[0]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
