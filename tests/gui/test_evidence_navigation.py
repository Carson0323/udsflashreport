from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QLabel, QPushButton

from flashreport_core.models import AnalysisResult, Finding, FrameEvidence, WindowEvidence
from flashreport_gui.main_window import MainWindow

from .test_main_window import _bundle


def test_frame_and_window_evidence_navigate_individually(qtbot, tmp_path) -> None:
    window = MainWindow(QSettings(str(tmp_path / "evidence.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    bundle = _bundle()
    frame = bundle.frames[0]
    finding = Finding(
        finding_id="ISO-TP-001",
        layer="ISO-TP",
        category="missing_fc_after_ff",
        deviation_ts=1.2,
        detected_ts=1.2,
        observed="none",
        expected="FC",
        suspected_side="ecu",
        confidence="medium",
        session=None,
        service=None,
        detail={},
        evidence=[
            FrameEvidence(
                frame_ref=frame.frame_ref,
                ts=frame.ts_seconds,
                line_no=frame.line_no,
                can_id=frame.can_id,
                role="tester->ecu",
                data=frame.data,
                summary="FF observed / 已观测 FF",
            ),
            WindowEvidence(
                ts_start=1.0,
                ts_end=1.2,
                expected_role="ecu->tester",
                expected_kind="FC",
                expected_can_id=0x456,
                matched_frame_count=0,
                trace_coverage_ok=True,
                summary="No FC in deadline / 截止时间内无 FC",
            ),
        ],
    )
    result = AnalysisResult(
        bundle=bundle,
        findings=[finding],
        first_deviation=finding,
        report_data={},
        frame_annotations=bundle.frame_annotations,
        conversation_summaries=bundle.conversation_summaries,
    )
    window.set_analysis_result(result)

    jump = window.findChild(QPushButton, "evidenceJump_ISO-TP-001_0")
    show = window.findChild(QPushButton, "evidenceShow_ISO-TP-001_1")
    assert jump is not None and show is not None
    qtbot.mouseClick(jump, Qt.MouseButton.LeftButton)
    assert window.frameTable.currentIndex().isValid()
    assert window.frameTable.currentIndex().row() == 0
    qtbot.mouseClick(show, Qt.MouseButton.LeftButton)
    assert window.detailTabs.currentWidget() is window.evidenceDetailTab
    assert "No FC in deadline" in window.findChild(QLabel, "evidenceDetailTabText").text()
