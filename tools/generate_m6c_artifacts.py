"""Generate local M6-C visual review artifacts from synthetic/public samples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from flashreport_core.api import analyze_trace, default_config, load_trace
from flashreport_core.models import AnalysisResult, Finding, FrameEvidence
from flashreport_gui.main_window import MainWindow


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
SCREENSHOTS = ARTIFACTS / "ui"


def synthetic_finding(bundle, finding_id: str = "FLASH-001") -> Finding:
    frame = bundle.frames[0]
    return Finding(
        finding_id=finding_id,
        layer="Flash",
        category="oversized_transfer_block",
        deviation_ts=frame.ts_seconds,
        detected_ts=frame.ts_seconds,
        observed="0x403 bytes",
        expected="<= 0x402 bytes",
        suspected_side="tester",
        confidence="high",
        session="programming",
        service="TransferData",
        detail={"synthetic": True},
        evidence=[
            FrameEvidence(
                frame_ref=frame.frame_ref,
                ts=frame.ts_seconds,
                line_no=frame.line_no,
                can_id=frame.can_id,
                role="tester->ecu",
                data=frame.data,
                summary="Synthetic evidence / 合成证据",
            )
        ],
    )


def make_window(app: QApplication, name: str) -> MainWindow:
    settings = QSettings(str(ARTIFACTS / f"{name}-settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    window.resize(1920, 1080)
    window.show()
    app.processEvents()
    return window


def capture(window: MainWindow, name: str, state: dict) -> None:
    app = QApplication.instance()
    assert app is not None
    app.processEvents()
    image = window.grab().scaled(1920, 1080, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    image.save(str(SCREENSHOTS / f"{name}.png"))
    state[name] = {
        "window_size": [window.width(), window.height()],
        "screenshot_size": [image.width(), image.height()],
        "state": window.state,
        "frame_count": window.frameModel.rowCount(),
        "finding_count": window.findingModel.rowCount(),
        "ambiguous_visible": window.ambiguousLabel.isVisible(),
    }
    window.close()


def main() -> int:
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    state: dict[str, dict] = {}

    empty = make_window(app, "empty")
    capture(empty, "empty", state)

    cfg = default_config()
    bundle = load_trace(str(ROOT / "samples" / "success_full_download.asc"), cfg)
    loaded = make_window(app, "loaded")
    loaded.set_bundle(bundle)
    capture(loaded, "loaded", state)

    finding_window = make_window(app, "finding")
    finding = synthetic_finding(bundle)
    finding_result = AnalysisResult(
        bundle=bundle,
        findings=[finding],
        first_deviation=finding,
        report_data={},
        frame_annotations=bundle.frame_annotations,
        conversation_summaries=bundle.conversation_summaries,
    )
    finding_window.set_analysis_result(finding_result)
    capture(finding_window, "finding", state)

    ambiguous_window = make_window(app, "ambiguous")
    ambiguous_result = AnalysisResult(
        bundle=bundle,
        findings=[finding],
        first_deviation=finding,
        report_data={"input_stats": {"ambiguous": True}},
        frame_annotations=bundle.frame_annotations,
        conversation_summaries=bundle.conversation_summaries,
    )
    ambiguous_window.set_analysis_result(ambiguous_result)
    capture(ambiguous_window, "ambiguous", state)

    error_window = make_window(app, "error")
    error_window._show_error("Synthetic parse failure / 合成解析失败")
    capture(error_window, "error", state)

    (ARTIFACTS / "M6-ui-state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
