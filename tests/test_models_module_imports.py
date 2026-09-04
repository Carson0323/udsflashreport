from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_models_imports_in_clean_python_process() -> None:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    completed = subprocess.run(
        [sys.executable, "-c", "import flashreport_core.models"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

