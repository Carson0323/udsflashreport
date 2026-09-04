from __future__ import annotations

from PySide6.QtCore import QSettings

from flashreport_gui.main_window import MainWindow


def test_frozen_ui_state_button_matrix(qtbot, tmp_path) -> None:
    window = MainWindow(QSettings(str(tmp_path / "state.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)

    assert window.statusState.text() == "EMPTY"
    assert window.openButton.isEnabled()
    assert not window.analyzeButton.isEnabled()
    assert not window.exportButton.isEnabled()

    window.set_state("LOADING")
    assert not window.openButton.isEnabled()
    assert not window.analyzeButton.isEnabled()
    assert not window.exportButton.isEnabled()

    window.set_bundle(window._bundle_for_test if hasattr(window, "_bundle_for_test") else _empty_bundle())
    assert window.statusState.text() == "READY"
    assert window.openButton.isEnabled()
    assert window.analyzeButton.isEnabled()
    assert not window.exportButton.isEnabled()


def _empty_bundle():
    from flashreport_core.models import TraceBundle, TraceQuality

    return TraceBundle(
        path="empty.asc",
        frames=[],
        conversations=[],
        quality=TraceQuality(
            start_ts=0.0,
            end_ts=0.0,
            has_capture_gap=None,
            dropped_frame_count=None,
            source_channels=[],
            filter_state_known=False,
            completeness="unknown",
        ),
        input_stats={},
        frame_annotations={},
        conversation_summaries=[],
    )
