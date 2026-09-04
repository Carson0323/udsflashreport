from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QLabel, QFrame, QPushButton, QScrollArea, QTableView, QTabWidget, QTreeView

from flashreport_core.models import (
    AnalysisResult,
    ConversationSummary,
    Finding,
    FrameAnnotation,
    FrameEvidence,
    RawFrame,
    TraceBundle,
    TraceQuality,
)
from flashreport_gui.main_window import MainWindow


def _bundle() -> TraceBundle:
    frame = RawFrame(
        ts_seconds=1.0,
        ts_display="1.000",
        source_ts_metadata={},
        can_id=0x123,
        is_extended=False,
        channel=1,
        is_fd=False,
        dlc=3,
        data=b"\x02\x10\x02",
        source="synthetic",
        line_no=1,
    )
    return TraceBundle(
        path="synthetic.asc",
        frames=[frame],
        conversations=[],
        quality=TraceQuality(
            start_ts=1.0,
            end_ts=1.0,
            has_capture_gap=None,
            dropped_frame_count=None,
            source_channels=[1],
            filter_state_known=False,
            completeness="unknown",
        ),
        input_stats={},
        frame_annotations={
            frame.frame_ref: FrameAnnotation(
                frame_ref=frame.frame_ref,
                direction="tester->ecu",
                isotp_summary="SF len=2",
                uds_summary=None,
                summary="SF len=2",
            )
        },
        conversation_summaries=[
            ConversationSummary(
                pair_key="1:123<->456",
                channel=1,
                name="ECU-A",
                request_id=0x123,
                response_id=0x456,
                is_extended_id=False,
                frame_count=1,
            )
        ],
    )


def test_main_window_exposes_frozen_object_names_and_empty_state(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)

    assert window.objectName() == "mainWindow"
    assert window.findChild(QTreeView, "conversationTree") is not None
    assert window.findChild(QTableView, "frameTable") is not None
    assert window.findChild(QScrollArea, "findingList") is not None
    assert window.findChild(QTabWidget, "detailTabs") is not None
    assert window.statusState.text() == "EMPTY"
    assert window.analyzeButton.isEnabled() is False
    assert window.exportButton.isEnabled() is False


def test_main_window_projects_bundle_and_finding_cards(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    bundle = _bundle()
    window.set_bundle(bundle)

    assert window.statusState.text() == "READY"
    assert window.frameModel.rowCount() == 1
    assert window.conversationModel.rowCount() == 1
    assert window.statusFrameCount.text().endswith("1")

    frame = bundle.frames[0]
    evidence = FrameEvidence(
        frame_ref=frame.frame_ref,
        ts=frame.ts_seconds,
        line_no=frame.line_no,
        can_id=frame.can_id,
        role="tester->ecu",
        data=frame.data,
        summary="Observed request / 观测到请求",
    )
    finding = Finding(
        finding_id="UDS-001",
        layer="UDS",
        category="test",
        deviation_ts=1.0,
        detected_ts=1.0,
        observed="request",
        expected="response",
        suspected_side="ecu",
        confidence="high",
        session=None,
        service="DiagnosticSessionControl",
        detail={},
        evidence=[evidence],
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

    assert window.statusState.text() == "RESULT"
    assert window.statusFindingCount.text().endswith("1")
    assert window.findChild(QFrame, "findingCard_UDS-001") is not None
    assert window.findChild(QPushButton, "evidenceJump_UDS-001_0") is not None


def test_large_finding_result_uses_virtual_list(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "large.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    bundle = _bundle()
    frame = bundle.frames[0]
    evidence = FrameEvidence(
        frame_ref=frame.frame_ref,
        ts=frame.ts_seconds,
        line_no=frame.line_no,
        can_id=frame.can_id,
        role="tester->ecu",
        data=frame.data,
        summary="Observed request / 观测到请求",
    )
    findings = [
        Finding(
            finding_id=f"UDS-{index:03d}",
            layer="UDS",
            category="test",
            deviation_ts=1.0 + index,
            detected_ts=1.0 + index,
            observed="request",
            expected="response",
            suspected_side="ecu",
            confidence="high",
            session=None,
            service="DiagnosticSessionControl",
            detail={},
            evidence=[evidence],
        )
        for index in range(101)
    ]
    result = AnalysisResult(
        bundle=bundle,
        findings=findings,
        first_deviation=findings[0],
        report_data={},
        frame_annotations=bundle.frame_annotations,
        conversation_summaries=bundle.conversation_summaries,
    )

    window.set_analysis_result(result)

    assert window.findingListView.isHidden() is False
    assert window.findingSummaryLabel.text().startswith("101 findings")
    assert window.findChild(QFrame, "findingCard_UDS-000") is None
    window.findingListView.setCurrentIndex(window.findingModel.index(0, 0))
    assert "Finding / 发现: UDS-000" in window.findChild(QLabel, "evidenceDetailTabText").text()
