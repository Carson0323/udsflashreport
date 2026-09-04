from __future__ import annotations

from PySide6.QtCore import QSettings

from flashreport_gui.main_window import MainWindow


def _window(qtbot, tmp_path) -> MainWindow:
    window = MainWindow(QSettings(str(tmp_path / "async.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    return window


def test_load_and_analyze_complete_through_qthreadpool_signals(qtbot, tmp_path) -> None:
    window = _window(qtbot, tmp_path)

    with qtbot.waitSignal(window.loadStarted, timeout=10_000):
        assert window.load_file("samples/success_full_download.asc")
    with qtbot.waitSignal(window.loadFinished, timeout=10_000) as loaded:
        qtbot.waitUntil(lambda: window.statusState.text() == "READY", timeout=10_000)

    assert loaded.args[0].frames
    assert window.frameModel.rowCount() > 0
    with qtbot.waitSignal(window.analysisFinished, timeout=10_000) as analyzed:
        assert window.start_analysis()
    assert analyzed.args[0].bundle is window._bundle
    assert window.statusState.text() == "RESULT"


def test_export_runs_asynchronously_and_emits_completion(qtbot, tmp_path) -> None:
    window = _window(qtbot, tmp_path)
    with qtbot.waitSignal(window.loadFinished, timeout=10_000):
        window.load_file("samples/success_full_download.asc")
    with qtbot.waitSignal(window.analysisFinished, timeout=10_000):
        window.start_analysis()

    md_path = tmp_path / "report.md"
    json_path = tmp_path / "report.json"
    with qtbot.waitSignal(window.exportFinished, timeout=10_000) as exported:
        assert window.export_files(str(md_path), str(json_path))

    assert exported.args[0]["validated"] is True
    assert md_path.is_file()
    assert json_path.is_file()
