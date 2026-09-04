from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtTest import QAbstractItemModelTester
from PySide6.QtWidgets import QFrame

from flashreport_core.models import AnalysisResult, Finding
from flashreport_gui.main_window import MainWindow

from .test_main_window import _bundle


def test_finding_panel_has_one_card_per_finding(qtbot, tmp_path) -> None:
    window = MainWindow(QSettings(str(tmp_path / "finding.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    bundle = _bundle()
    findings = [
        Finding(
            finding_id="UDS-001",
            layer="UDS",
            category="timeout",
            deviation_ts=1.0,
            detected_ts=1.0,
            observed="timeout",
            expected="response",
            suspected_side="ecu",
            confidence="low",
            session=None,
            service=None,
            detail={},
            evidence=[],
        ),
        Finding(
            finding_id="FLASH-001",
            layer="Flash",
            category="oversized",
            deviation_ts=2.0,
            detected_ts=2.0,
            observed="0x403",
            expected="<= 0x402",
            suspected_side="tester",
            confidence="high",
            session="programming",
            service="TransferData",
            detail={},
            evidence=[],
        ),
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
    tester = QAbstractItemModelTester(
        window.findingModel,
        QAbstractItemModelTester.FailureReportingMode.Warning,
        window.findingModel,
    )

    assert window.findingModel.rowCount() == 2
    assert window.findChild(QFrame, "findingCard_UDS-001") is not None
    assert window.findChild(QFrame, "findingCard_FLASH-001") is not None
    window.findingModel.set_findings([])
    assert window.findingModel.rowCount() == 0
