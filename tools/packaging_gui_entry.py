"""Import-safe GUI entry point for PyInstaller / PyInstaller 可安全导入入口。"""

from __future__ import annotations

import os
import sys

from flashreport_core.api import analyze_trace, default_config, export_report, load_trace
from flashreport_gui.app import create_application, main


def _run_analysis_smoke_if_requested() -> int | None:
    """Exercise bundled findings and report schemas when requested by the builder."""
    path = os.environ.get("FLASHREPORT_SMOKE_ANALYSIS_FILE")
    if not path:
        return None
    config = default_config()
    result = analyze_trace(load_trace(path, config), config)
    export_report(result, None, None)
    return 0


def _run_smoke_if_requested() -> int | None:
    """Run a short, deterministic startup check when requested by the builder."""
    value = os.environ.get("FLASHREPORT_SMOKE_MS")
    if not value:
        return None
    try:
        duration_ms = max(1, int(value))
    except ValueError:
        return None

    from PySide6.QtCore import QTimer

    app, window = create_application(sys.argv)
    window.show()
    QTimer.singleShot(duration_ms, app.quit)
    return app.exec()


if __name__ == "__main__":
    analysis_smoke_result = _run_analysis_smoke_if_requested()
    smoke_result = _run_smoke_if_requested()
    if analysis_smoke_result is not None and analysis_smoke_result != 0:
        raise SystemExit(analysis_smoke_result)
    raise SystemExit(main() if smoke_result is None else smoke_result)
