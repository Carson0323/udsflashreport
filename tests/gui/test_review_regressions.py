from dataclasses import replace

from PySide6.QtCore import QSettings

from flashreport_core.api import default_config
from flashreport_gui.main_window import MainWindow


def test_configuration_change_reloads_addressing_and_invalidates_result(qtbot, tmp_path):
    window = MainWindow(QSettings(str(tmp_path / "review.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    with qtbot.waitSignal(window.loadFinished):
        window.load_file("samples/success_full_download.asc")
    with qtbot.waitSignal(window.analysisFinished):
        window.start_analysis()
    cfg = replace(window.config, addressing=replace(window.config.addressing, auto_detect=False))
    with qtbot.waitSignal(window.loadFinished):
        window._on_config_saved(cfg)
    assert window._analysis_result is None
    assert not window.exportButton.isEnabled()
    assert window._bundle.conversations == []


def test_explicit_load_config_is_used_for_analysis_and_busy_load_rejected(qtbot, tmp_path):
    window = MainWindow(QSettings(str(tmp_path / "review.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    cfg = replace(default_config(), timeouts=replace(default_config().timeouts, uds_p2_ms=123))
    with qtbot.waitSignal(window.loadFinished):
        assert window.load_file("samples/success_full_download.asc", cfg)
        assert not window.load_file("samples/ok_success_full_download.asc")
    assert window.config == cfg
