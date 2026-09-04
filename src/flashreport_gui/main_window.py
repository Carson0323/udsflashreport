"""Main Qt Widgets shell / 主窗口 Qt Widgets 外壳。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
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

from flashreport_core.models import AnalysisResult, Evidence, Finding, RawFrame, TraceBundle

from .models import (
    AnnotationRole,
    ConversationTreeModel,
    FindingListModel,
    FrameFilterProxyModel,
    FrameObjectRole,
    FrameTableModel,
)


class MainWindow(QMainWindow):
    """M6-A frozen layout and API-object projection.

    Loading, analysis and export workers are intentionally left for M6-B. The
    public setters make this shell directly testable and keep the view free of
    protocol interpretation / M6-B 的线程工作器将在此壳上接入。
    """

    def __init__(self, settings: QSettings | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mainWindow")
        self.setWindowTitle("FlashReport / UDS 刷写 Trace 分析")
        self.resize(1440, 900)
        self._settings = settings or QSettings()
        self._bundle: TraceBundle | None = None
        self._analysis_result: AnalysisResult | None = None

        self._build_toolbar()
        self._build_models()
        self._build_central_layout()
        self._build_status_bar()
        self._restore_ui_state()
        self.set_state("EMPTY")

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
        self.frameTable.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.frameTable.setAlternatingRowColors(True)
        self.frameTable.setSortingEnabled(True)
        self.frameTable.setWordWrap(False)
        self.frameTable.verticalHeader().setVisible(False)
        self.frameTable.horizontalHeader().setStretchLastSection(True)
        self.frameTable.setMinimumWidth(520)
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

    def set_state(self, state: str) -> None:
        """Apply the frozen M6 state/button matrix / 应用 M6 状态机按钮矩阵。"""

        state = state.upper()
        has_bundle = self._bundle is not None
        self.statusState.setText(state)
        self.openButton.setEnabled(state not in {"LOADING", "ANALYZING"})
        self.analyzeButton.setEnabled(has_bundle and state in {"READY", "RESULT", "ERROR"})
        self.exportButton.setEnabled(state == "RESULT" and self._analysis_result is not None)
        self.settingsButton.setEnabled(state not in {"LOADING", "ANALYZING"})

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
        self.set_state("READY")

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
        self.set_state("RESULT")

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
        else:
            button.setText("Show / 查看")
            button.setObjectName(f"evidenceShow_{finding.finding_id}_{index}")
        button.setEnabled(False)
        row_layout.addWidget(button)
        layout.addWidget(row)

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
