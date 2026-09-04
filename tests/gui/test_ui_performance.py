from __future__ import annotations

from PySide6.QtCore import QSettings

from flashreport_gui.main_window import MainWindow


def test_heartbeat_timer_stays_active_during_async_load(qtbot, tmp_path) -> None:
    window = MainWindow(QSettings(str(tmp_path / "performance.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    assert window._heartbeat_timer.interval() == 50
    with qtbot.waitSignal(window.loadFinished, timeout=10_000):
        window.load_file("samples/success_full_download.asc")
    qtbot.wait(75)
    assert window.heartbeatMaxGapMs < 500
