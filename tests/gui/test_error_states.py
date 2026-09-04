from __future__ import annotations

from PySide6.QtCore import QSettings

from flashreport_gui.main_window import MainWindow


def test_parse_failure_enters_error_state_without_crashing(qtbot, tmp_path) -> None:
    window = MainWindow(QSettings(str(tmp_path / "error.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)

    with qtbot.waitSignal(window.loadFailed, timeout=10_000) as failed:
        window.load_file(str(tmp_path / "missing.asc"))

    assert failed.args[0]
    assert window.statusState.text() == "ERROR"
    assert "无法加载" in window.errorLabel.text()
    assert window.openButton.isEnabled()
    assert not window.analyzeButton.isEnabled()
    assert not window.exportButton.isEnabled()
