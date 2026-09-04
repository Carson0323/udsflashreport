"""Main Qt Widgets shell / 主窗口 Qt Widgets 外壳。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QItemSelectionModel, QSettings, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableView,
    QToolBar,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from flashreport_core.models import AnalysisResult, AppConfig, Evidence, Finding, RawFrame, TraceBundle

from .controllers import AnalysisController, ExportController
from .dialogs import ConfigDialog, load_persisted_config
from .models import (
    AnnotationRole,
    ConversationTreeModel,
    FindingListModel,
    FrameFilterProxyModel,
    FrameObjectRole,
    FrameRefRole,
    FrameTableModel,
)


class MainWindow(QMainWindow):
    """M6-A frozen layout and API-object projection.

    Loading, analysis and export are scheduled through QThreadPool controllers.
    The view remains a projection of public API/model objects and never performs
    protocol interpretation / 所有耗时操作走 QThreadPool，界面只投影 public
    API/model 对象，不在 GUI 内推导协议语义。
    """

    loadStarted = Signal()  # noqa: N815
    loadFinished = Signal(object)  # noqa: N815
    loadFailed = Signal(str)  # noqa: N815
    analysisStarted = Signal()  # noqa: N815
    analysisFinished = Signal(object)  # noqa: N815
    analysisFailed = Signal(str)  # noqa: N815
    exportStarted = Signal()  # noqa: N815
    exportFinished = Signal(object)  # noqa: N815
    exportFailed = Signal(str)  # noqa: N815

    _ALLOWED_TRANSITIONS = {
        "EMPTY": {"EMPTY", "LOADING"},
        "LOADING": {"LOADING", "READY", "ERROR"},
        "READY": {"READY", "LOADING", "ANALYZING", "ERROR"},
        "ANALYZING": {"ANALYZING", "RESULT", "ERROR"},
        "RESULT": {"RESULT", "LOADING", "ANALYZING", "ERROR"},
        "ERROR": {"ERROR", "LOADING", "EMPTY"},
    }

    def __init__(self, settings: QSettings | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mainWindow")
        self.setWindowTitle("FlashReport / UDS 刷写 Trace 分析")
        self.resize(1440, 900)
        self._settings = settings or QSettings()
        self._bundle: TraceBundle | None = None
        self._analysis_result: AnalysisResult | None = None
        self._config = load_persisted_config(self._settings)
        self._state = "EMPTY"
        self._active_path: str | None = None
        self._exporting = False
        self.heartbeatMaxGapMs = 0.0  # noqa: N815
        self._heartbeat_last = monotonic()
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(50)
        self._heartbeat_timer.timeout.connect(self._record_heartbeat)
        self._heartbeat_timer.start()

        self.analysisController = AnalysisController(parent=self)
        self.exportController = ExportController(parent=self)
        self.analysis_controller = self.analysisController
        self.export_controller = self.exportController
        self.analysisController.loadStarted.connect(self._on_load_started)
        self.analysisController.loadFinished.connect(self._on_load_finished)
        self.analysisController.loadFailed.connect(self._on_load_failed)
        self.analysisController.analysisStarted.connect(self._on_analysis_started)
        self.analysisController.analysisFinished.connect(self._on_analysis_finished)
        self.analysisController.analysisFailed.connect(self._on_analysis_failed)
        self.exportController.exportStarted.connect(self._on_export_started)
        self.exportController.exportFinished.connect(self._on_export_finished)
        self.exportController.exportFailed.connect(self._on_export_failed)

        self._build_toolbar()
        self._build_models()
        self._build_central_layout()
        self._build_status_bar()
        self._restore_ui_state()
        self.set_state("EMPTY")
        self.openButton.clicked.connect(self._open_file_dialog)
        self.analyzeButton.clicked.connect(self.start_analysis)
        self.exportButton.clicked.connect(self._export_file_dialog)
        self.settingsButton.clicked.connect(self._open_settings_dialog)

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar("FlashReport / 工具栏", self)
        self.toolbar.setObjectName("toolbar")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(self.toolbar)
        self.openButton = self._toolbar_button("Open / 打开", "openButton")
        self.analyzeButton = self._toolbar_button("Analyze / 分析", "analyzeButton")
        self.exportButton = self._toolbar_button("Export / 导出", "exportButton")
        self.settingsButton = self._toolbar_button("Settings / 设置", "settingsButton")

    def _toolbar_button(self, text: str, object_name: str) -> QPushButton:
        button = QPushButton(text, self.toolbar)
        button.setObjectName(object_name)
        self.toolbar.addWidget(button)
        return button

    @property
    def state(self) -> str:
        """Current frozen UI state / 当前冻结界面状态。"""

        return self._state

    @property
    def config(self) -> AppConfig:
        return self._config

    def _build_models(self) -> None:
        self.frameModel = FrameTableModel()
        self.frameProxyModel = FrameFilterProxyModel(self)
        self.frameProxyModel.setSourceModel(self.frameModel)
        self.conversationModel = ConversationTreeModel()
        self.findingModel = FindingListModel()

    def _build_central_layout(self) -> None:
        root_splitter = QSplitter(Qt.Orientation.Vertical, self)
        root_splitter.setObjectName("detailSplitter")

        main_splitter = QSplitter(Qt.Orientation.Horizontal, root_splitter)
        main_splitter.setObjectName("mainSplitter")
        main_splitter.setChildrenCollapsible(False)

        self.conversationTree = QTreeView(main_splitter)
        self.conversationTree.setObjectName("conversationTree")
        self.conversationTree.setModel(self.conversationModel)
        self.conversationTree.setHeaderHidden(True)
        self.conversationTree.setUniformRowHeights(True)
        self.conversationTree.setMinimumWidth(190)

        frame_panel = QWidget(main_splitter)
        frame_panel.setObjectName("framePanel")
        frame_layout = QVBoxLayout(frame_panel)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(4)
        self.frameTable = QTableView(frame_panel)
        self.frameTable.setObjectName("frameTable")
        self.frameTable.setModel(self.frameProxyModel)
        self.frameTable.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.frameTable.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.frameTable.setAlternatingRowColors(True)
        self.frameTable.setSortingEnabled(True)
        self.frameTable.setWordWrap(False)
        self.frameTable.verticalHeader().setVisible(False)
        self.frameTable.horizontalHeader().setStretchLastSection(True)
        self.frameTable.setMinimumWidth(520)
        self.emptyCenterLabel = QLabel(
            "Open an ASC/BLF trace to begin / 请打开 ASC/BLF Trace 开始分析",
            frame_panel,
        )
        self.emptyCenterLabel.setObjectName("emptyCenterState")
        self.emptyCenterLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.emptyCenterLabel.setWordWrap(True)
        self.errorLabel = QLabel(frame_panel)
        self.errorLabel.setObjectName("errorMessage")
        self.errorLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.errorLabel.setWordWrap(True)
        self.errorLabel.setVisible(False)
        frame_layout.addWidget(self.emptyCenterLabel)
        frame_layout.addWidget(self.errorLabel)
        frame_layout.addWidget(self.frameTable)

        self.findingList = QScrollArea(main_splitter)
        self.findingList.setObjectName("findingList")
        self.findingList.setWidgetResizable(True)
        self.findingList.setMinimumWidth(300)
        self.findingListWidget = QWidget()
        self.findingListWidget.setObjectName("findingListWidget")
        self.findingListLayout = QVBoxLayout(self.findingListWidget)
        self.findingListLayout.setContentsMargins(8, 8, 8, 8)
        self.findingListLayout.setSpacing(8)
        self.findingListLayout.addStretch(1)
        self.findingList.setWidget(self.findingListWidget)

        main_splitter.setSizes([240, 760, 400])
        root_splitter.addWidget(main_splitter)

        self.detailTabs = QTabWidget(root_splitter)
        self.detailTabs.setObjectName("detailTabs")
        self._add_detail_tab("frameDetailTab", "Frame Details / 帧详情", "Select a frame / 请选择一帧")
        self._add_detail_tab("isotpDetailTab", "ISO-TP", "No ISO-TP detail / 暂无 ISO-TP 详情")
        self._add_detail_tab("udsDetailTab", "UDS", "No UDS detail / 暂无 UDS 详情")
        self._add_detail_tab("sessionDetailTab", "Session / 会话", "No session detail / 暂无会话详情")
        self._add_detail_tab("evidenceDetailTab", "Evidence / 证据", "Select evidence / 请选择证据")
        root_splitter.setSizes([620, 240])
        self._rootSplitter = root_splitter
        self.setCentralWidget(root_splitter)

        selection = self.frameTable.selectionModel()
        if selection is not None:
            selection.currentChanged.connect(self._show_selected_frame)

    def _add_detail_tab(self, object_name: str, title: str, text: str) -> None:
        tab = QWidget(self.detailTabs)
        tab.setObjectName(object_name)
        setattr(self, object_name, tab)
        layout = QVBoxLayout(tab)
        label = QLabel(text, tab)
        label.setObjectName(f"{object_name}Text")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(label)
        layout.addStretch(1)
        self.detailTabs.addTab(tab, title)

    def _build_status_bar(self) -> None:
        status = self.statusBar()
        self.statusFrameCount = QLabel("Frames / 帧: 0", status)
        self.statusFrameCount.setObjectName("statusFrameCount")
        self.statusFindingCount = QLabel("Findings / 发现: 0", status)
        self.statusFindingCount.setObjectName("statusFindingCount")
        self.statusState = QLabel("EMPTY", status)
        self.statusState.setObjectName("statusState")
        self.statusChannel = QLabel("Channel / 通道: —", status)
        self.statusChannel.setObjectName("statusChannel")
        status.addPermanentWidget(self.statusFrameCount)
        status.addPermanentWidget(self.statusFindingCount)
        status.addPermanentWidget(self.statusState)
        status.addPermanentWidget(self.statusChannel)

    def set_state(self, state: str, *, force: bool = False) -> bool:
        """Apply the frozen M6 state/button matrix / 应用 M6 状态机按钮矩阵。"""

        state = state.upper()
        if state not in self._ALLOWED_TRANSITIONS:
            return False
        if not force and state not in self._ALLOWED_TRANSITIONS.get(self._state, set()):
            return False
        self._state = state
        has_bundle = self._bundle is not None
        self.statusState.setText(state)
        self.openButton.setEnabled(state not in {"LOADING", "ANALYZING"})
        self.analyzeButton.setEnabled(has_bundle and state in {"READY", "RESULT"})
        self.exportButton.setEnabled(state == "RESULT" and self._analysis_result is not None)
        self.settingsButton.setEnabled(state not in {"LOADING", "ANALYZING"})
        self.emptyCenterLabel.setVisible(state in {"EMPTY", "LOADING", "ANALYZING"})
        self.errorLabel.setVisible(state == "ERROR")
        self.frameTable.setVisible(state not in {"EMPTY", "ERROR", "LOADING"})
        return True

    def set_bundle(self, bundle: TraceBundle) -> None:
        """Project a loaded API bundle into the frozen UI / 将 API bundle 投影到界面。"""

        self._bundle = bundle
        self._analysis_result = None
        self.frameModel.set_data(bundle.frames, bundle.frame_annotations, bundle.quality.start_ts)
        self.conversationModel.set_summaries(bundle.conversation_summaries)
        self.findingModel.set_findings(())
        self._render_findings(())
        self.statusFrameCount.setText(f"Frames / 帧: {len(bundle.frames)}")
        self.statusFindingCount.setText("Findings / 发现: 0")
        self._update_channel_status(bundle)
        self.set_state("READY", force=True)

    def set_analysis_result(self, result: AnalysisResult) -> None:
        """Project analysis output and render evidence cards / 展示分析结果和证据卡片。"""

        self._analysis_result = result
        self._bundle = result.bundle
        annotations = result.frame_annotations or result.bundle.frame_annotations
        self.frameModel.set_data(result.bundle.frames, annotations, result.bundle.quality.start_ts)
        self.conversationModel.set_summaries(result.conversation_summaries or result.bundle.conversation_summaries)
        self.findingModel.set_findings(result.findings)
        self._render_findings(result.findings)
        self.statusFrameCount.setText(f"Frames / 帧: {len(result.bundle.frames)}")
        self.statusFindingCount.setText(f"Findings / 发现: {len(result.findings)}")
        self._update_channel_status(result.bundle)
        self.set_state("RESULT", force=True)

    # ---------- asynchronous interaction / 异步交互 ----------
    def _open_file_dialog(self) -> None:
        start = self._settings.value("ui/last_open_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open trace / 打开 Trace",
            str(start),
            "Trace files (*.asc *.blf);;ASC (*.asc);;BLF (*.blf);;All files (*)",
        )
        if path:
            self.load_file(path)

    def load_file(self, path: str, config: AppConfig | None = None) -> bool:
        """Load a trace through the AnalysisController worker."""

        if not path:
            return False
        selected_config = config if config is not None else self._config
        self._active_path = str(path)
        self._bundle = None
        self._analysis_result = None
        self.frameModel.set_data((), {}, 0.0)
        self.conversationModel.set_summaries(())
        self.findingModel.set_findings(())
        self._render_findings(())
        self.set_state("LOADING", force=True)
        self.analysisController.load_file(str(path), selected_config)
        return True

    # Alias used by callers that describe the action as opening a path.
    open_file = load_file
    load_trace_async = load_file

    def start_analysis(self) -> bool:
        """Analyze the current bundle on a QThreadPool worker."""

        if self._bundle is None or self._state not in {"READY", "RESULT"}:
            return False
        self.analysisController.analyze(self._bundle, self._config)
        return True

    analyze = start_analysis
    analyze_async = start_analysis

    def export_files(self, md_path: str | None, json_path: str | None) -> bool:
        """Export the current result through the ExportController worker."""

        if self._analysis_result is None or self._state != "RESULT" or self._exporting:
            return False
        self.exportController.export(self._analysis_result, md_path, json_path)
        return True

    export = export_files
    export_async = export_files

    def _export_file_dialog(self) -> None:
        if self._analysis_result is None:
            return
        start = self._settings.value("ui/last_open_dir", "flashreport-report.md")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export report / 导出报告",
            str(start),
            "Markdown (*.md);;JSON (*.json)",
        )
        if not path:
            return
        selected = Path(path)
        if selected.suffix.lower() == ".json":
            md_path, json_path = str(selected.with_suffix(".md")), str(selected)
        else:
            md_path, json_path = str(selected), str(selected.with_suffix(".json"))
        self._settings.setValue("ui/last_open_dir", str(selected.parent))
        self.export_files(md_path, json_path)

    def _open_settings_dialog(self) -> None:
        dialog = ConfigDialog(self._config, self._settings, self)
        dialog.configSaved.connect(self._on_config_saved)
        dialog.exec()

    @Slot(object)
    def _on_config_saved(self, config: AppConfig) -> None:
        self._config = config
        self.statusBar().showMessage("Configuration updated / 配置已更新", 4000)

    @Slot()
    def _on_load_started(self) -> None:
        self._begin_busy_interval()
        self.emptyCenterLabel.setText("Loading trace… / 正在加载 Trace…")
        self.set_state("LOADING")
        self.loadStarted.emit()

    @Slot(object)
    def _on_load_finished(self, bundle: object) -> None:
        if not isinstance(bundle, TraceBundle):
            self._show_error("Invalid loader result / 加载器返回结果无效")
            return
        self.set_bundle(bundle)
        if self._active_path:
            self._settings.setValue("ui/last_open_dir", str(Path(self._active_path).parent))
        self.statusBar().showMessage("Trace loaded / Trace 已加载", 4000)
        self.loadFinished.emit(bundle)

    @Slot(str)
    def _on_load_failed(self, message: str) -> None:
        self._show_error(f"Unable to load trace / 无法加载 Trace:\n{message}")
        self.loadFailed.emit(message)

    @Slot()
    def _on_analysis_started(self) -> None:
        self._begin_busy_interval()
        self.emptyCenterLabel.setText("Analyzing… / 正在分析…")
        self.set_state("ANALYZING")
        self.analysisStarted.emit()

    @Slot(object)
    def _on_analysis_finished(self, result: object) -> None:
        if not isinstance(result, AnalysisResult):
            self._show_error("Invalid analysis result / 分析结果无效")
            return
        self.set_analysis_result(result)
        self.statusBar().showMessage("Analysis completed / 分析完成", 4000)
        self.analysisFinished.emit(result)

    @Slot(str)
    def _on_analysis_failed(self, message: str) -> None:
        self._show_error(f"Analysis failed / 分析失败:\n{message}")
        self.analysisFailed.emit(message)

    @Slot()
    def _on_export_started(self) -> None:
        self._begin_busy_interval()
        self._exporting = True
        self.openButton.setEnabled(False)
        self.analyzeButton.setEnabled(False)
        self.exportButton.setEnabled(False)
        self.statusBar().showMessage("Exporting report… / 正在导出报告…")
        self.exportStarted.emit()

    @Slot(object)
    def _on_export_finished(self, value: object) -> None:
        self._exporting = False
        self.set_state("RESULT")
        self.statusBar().showMessage("Report exported / 报告已导出", 5000)
        self.exportFinished.emit(value)

    @Slot(str)
    def _on_export_failed(self, message: str) -> None:
        self._exporting = False
        self._show_error(f"Export failed / 导出失败:\n{message}")
        self.exportFailed.emit(message)

    def _show_error(self, message: str) -> None:
        self.errorLabel.setText(message)
        self.findingModel.set_findings(())
        self._render_findings(())
        self.set_state("ERROR")

    def _record_heartbeat(self) -> None:
        now = monotonic()
        gap_ms = (now - self._heartbeat_last) * 1000.0
        if self.statusState.text() in {"LOADING", "ANALYZING"} or self._exporting:
            self.heartbeatMaxGapMs = max(self.heartbeatMaxGapMs, gap_ms)
        self._heartbeat_last = now

    def _begin_busy_interval(self) -> None:
        self._heartbeat_last = monotonic()
        self.heartbeatMaxGapMs = 0.0

    def _update_channel_status(self, bundle: TraceBundle) -> None:
        channels = ", ".join(str(channel) for channel in bundle.quality.source_channels) or "—"
        self.statusChannel.setText(f"Channel / 通道: {channels}")

    def _clear_finding_cards(self) -> None:
        while self.findingListLayout.count():
            item = self.findingListLayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.findingListLayout.addStretch(1)

    def _render_findings(self, findings: Sequence[Finding]) -> None:
        self._clear_finding_cards()
        if not findings:
            empty = QLabel("No findings / 未发现问题", self.findingListWidget)
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            self.findingListLayout.insertWidget(0, empty)
            return
        for finding in findings:
            self.findingListLayout.insertWidget(self.findingListLayout.count() - 1, self._finding_card(finding))

    def _finding_card(self, finding: Finding) -> QFrame:
        card = QFrame(self.findingListWidget)
        card.setObjectName(f"findingCard_{finding.finding_id}")
        card.setProperty("severity", finding.confidence.lower())
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        title = QLabel(f"{finding.finding_id} / {finding.layer}", card)
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)
        meta = QLabel(
            f"Confidence / 置信度: {finding.confidence} · "
            f"Side / 责任侧: {finding.suspected_side}",
            card,
        )
        meta.setObjectName("secondaryText")
        meta.setWordWrap(True)
        layout.addWidget(meta)
        observed = QLabel(f"Observed / 观测: {finding.observed}\nExpected / 期望: {finding.expected}", card)
        observed.setWordWrap(True)
        layout.addWidget(observed)
        for index, evidence in enumerate(finding.evidence):
            self._add_evidence_row(layout, finding, evidence, index)
        return card

    def _add_evidence_row(self, layout: QVBoxLayout, finding: Finding, evidence: Evidence, index: int) -> None:
        row = QFrame(self.findingListWidget)
        row.setObjectName(f"evidenceItem_{finding.finding_id}_{index}")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        summary = QLabel(getattr(evidence, "summary", "Evidence / 证据"), row)
        summary.setWordWrap(True)
        row_layout.addWidget(summary, 1)
        button = QPushButton(row)
        if getattr(evidence, "type", None) == "frame":
            button.setText("Jump / 跳转")
            button.setObjectName(f"evidenceJump_{finding.finding_id}_{index}")
            button.clicked.connect(lambda _checked=False, item=evidence: self.jump_to_frame(item))
        else:
            button.setText("Show / 查看")
            button.setObjectName(f"evidenceShow_{finding.finding_id}_{index}")
            button.clicked.connect(lambda _checked=False, item=evidence: self.show_interval(item))
        button.setEnabled(True)
        row_layout.addWidget(button)
        layout.addWidget(row)

    def jump_to_frame(self, evidence: object) -> bool:
        """Select the exact FrameEvidence row / 选中 FrameEvidence 对应的精确帧。"""

        frame_ref = getattr(evidence, "frame_ref", evidence if isinstance(evidence, str) else None)
        if not frame_ref:
            return False
        source_index = None
        for row in range(self.frameModel.rowCount()):
            candidate = self.frameModel.index(row, 0)
            if self.frameModel.data(candidate, FrameRefRole) == frame_ref:
                source_index = candidate
                break
        if source_index is None:
            return False
        proxy_index = self.frameProxyModel.mapFromSource(source_index)
        if not proxy_index.isValid():
            self.frameProxyModel.set_query("")
            proxy_index = self.frameProxyModel.mapFromSource(source_index)
        if not proxy_index.isValid():
            return False
        selection = self.frameTable.selectionModel()
        if selection is not None:
            selection.clearSelection()
            selection.select(proxy_index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.frameTable.setCurrentIndex(proxy_index)
        self.frameTable.scrollTo(proxy_index, QTableView.ScrollHint.PositionAtCenter)
        self.detailTabs.setCurrentWidget(self.frameDetailTab)
        return True

    def show_interval(self, evidence: object) -> bool:
        """Highlight the observed window and explain the absence / 高亮区间并说明缺失。"""

        start = getattr(evidence, "ts_start", None)
        end = getattr(evidence, "ts_end", None)
        if start is None or end is None:
            return False
        matching_rows = []
        for row in range(self.frameModel.rowCount()):
            frame = self.frameModel.frame_at(row)
            if frame is not None and start <= frame.ts_seconds <= end:
                matching_rows.append(row)
        selection = self.frameTable.selectionModel()
        if selection is not None:
            selection.clearSelection()
            for row in matching_rows:
                source_index = self.frameModel.index(row, 0)
                proxy_index = self.frameProxyModel.mapFromSource(source_index)
                if proxy_index.isValid():
                    selection.select(
                        proxy_index,
                        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                    )
            if matching_rows:
                first = self.frameProxyModel.mapFromSource(self.frameModel.index(matching_rows[0], 0))
                last = self.frameProxyModel.mapFromSource(self.frameModel.index(matching_rows[-1], 0))
                if first.isValid():
                    self.frameTable.setCurrentIndex(first)
                    self.frameTable.scrollTo(first, QTableView.ScrollHint.PositionAtCenter)
                if last.isValid():
                    self.frameTable.scrollTo(last, QTableView.ScrollHint.PositionAtCenter)
        detail = self.findChild(QLabel, "evidenceDetailTabText")
        if detail is not None:
            detail.setText(
                f"Absence window / 缺失区间: {start:.6f}s – {end:.6f}s\n"
                f"Expected role / 期望方向: {getattr(evidence, 'expected_role', 'unknown')}\n"
                f"Expected kind / 期望类型: {getattr(evidence, 'expected_kind', 'unknown')}\n"
                f"Matched frames / 命中帧数: {getattr(evidence, 'matched_frame_count', len(matching_rows))}\n"
                f"Coverage OK / 覆盖完整: {getattr(evidence, 'trace_coverage_ok', None)}\n"
                f"{getattr(evidence, 'summary', '')}"
            )
        self.detailTabs.setCurrentWidget(self.evidenceDetailTab)
        return True

    def _show_selected_frame(self, current: object, previous: object) -> None:
        del previous
        index = current
        if not hasattr(index, "isValid") or not index.isValid():
            return
        frame = index.data(FrameObjectRole)
        if not isinstance(frame, RawFrame):
            return
        annotation = index.data(AnnotationRole)
        detail = self.findChild(QLabel, "frameDetailTabText")
        if detail is None:
            return
        detail.setText(
            f"Frame / 帧: {frame.frame_ref}\n"
            f"Time / 时间: {frame.ts_display} ({frame.ts_seconds:.6f}s)\n"
            f"Channel / 通道: {frame.channel}\n"
            f"CAN ID: {frame.can_id:X}\n"
            f"DLC: {frame.dlc}\n"
            f"Data / 数据: {' '.join(f'{byte:02X}' for byte in frame.data)}\n"
            f"Summary / 摘要: {getattr(annotation, 'summary', 'other')}"
        )

    def _restore_ui_state(self) -> None:
        geometry = self._settings.value("ui/main_window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self._settings.value("ui/main_splitter_state")
        if splitter_state:
            self.findChild(QSplitter, "mainSplitter").restoreState(splitter_state)
        detail_state = self._settings.value("ui/detail_splitter_state")
        if detail_state:
            self._rootSplitter.restoreState(detail_state)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._settings.setValue("ui/main_window_geometry", self.saveGeometry())
        self._settings.setValue("ui/main_splitter_state", self.findChild(QSplitter, "mainSplitter").saveState())
        self._settings.setValue("ui/detail_splitter_state", self._rootSplitter.saveState())
        super().closeEvent(event)
