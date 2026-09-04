"""Application entry point / GUI 应用入口。"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import apply_theme


def create_application(argv: Sequence[str] | None = None) -> tuple[QApplication, MainWindow]:
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
    QCoreApplication.setOrganizationName("flashreport")
    QCoreApplication.setOrganizationDomain("flashreport.local")
    QCoreApplication.setApplicationName("flashreport")
    apply_theme(app)
    return app, MainWindow()


def main(argv: Sequence[str] | None = None) -> int:
    app, window = create_application(argv)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
