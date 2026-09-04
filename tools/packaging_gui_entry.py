"""Import-safe GUI entry point for PyInstaller / PyInstaller 可安全导入入口。"""

from __future__ import annotations

import os
import sys

from flashreport_gui.app import create_application, main


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
    smoke_result = _run_smoke_if_requested()
    raise SystemExit(main() if smoke_result is None else smoke_result)
