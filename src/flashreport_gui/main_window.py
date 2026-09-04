"""Main Qt Widgets shell / 主窗口 Qt Widgets 外壳。"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QSettings, QSize, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
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
    FindingRole,
    FrameFilterProxyModel,
    FrameObjectRole,
    FrameRefRole,
    FrameTableDelegate,
    FrameTableModel,
)
from .i18n import LANGUAGE_CODES, LANGUAGE_LABELS, tr
from .theme import DARK_TOKENS, LIGHT_TOKENS, apply_theme, icon_for


WORKFLOW_COLUMNS = ("Step", "Time", "Addressing", "Service", "Description", "Status", "Evidence")


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
        self.setMinimumSize(1100, 650)
        self._settings = settings or QSettings()
        stored_language = str(self._settings.value("ui/language", "zh")).casefold()
        self._language = stored_language if stored_language in LANGUAGE_CODES else "zh"
        self._dark_mode = self._setting_bool(self._settings.value("ui/dark_mode", False))
        self._theme_tokens = DARK_TOKENS if self._dark_mode else LIGHT_TOKENS
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._theme_tokens)
        self._bundle: TraceBundle | None = None
        self._analysis_result: AnalysisResult | None = None
        self._config = load_persisted_config(self._settings)
        self._state = "EMPTY"
        self._active_path: str | None = None
        self._exporting = False
        self._finding_card_limit = 100
        self._workflow_steps: list[dict] = []
        self._last_error_message = ""
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
        self.themeButton.clicked.connect(self._toggle_theme)
        self.languageCombo.currentIndexChanged.connect(self._on_language_changed)
        self._retranslate_ui()

    @staticmethod
    def _setting_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"1", "true", "yes", "on"}

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar("FlashReport / 工具栏", self)
        self.toolbar.setObjectName("toolbar")
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(self.toolbar)
        self.brandIcon = QLabel(self.toolbar)
        self.brandIcon.setObjectName("brandIcon")
        self.brandIcon.setPixmap(icon_for("flashreport", self._theme_tokens).pixmap(20, 20))
        self.toolbar.addWidget(self.brandIcon)
        self.brandLabel = QLabel(self.toolbar)
        self.brandLabel.setObjectName("brandLabel")
        self.toolbar.addWidget(self.brandLabel)
        self.openButton = self._toolbar_button("Open / 打开", "openButton")
        self.analyzeButton = self._toolbar_button("Analyze / 分析", "analyzeButton")
        self.exportButton = self._toolbar_button("Export / 导出", "exportButton")
        self.settingsButton = self._toolbar_button("Settings / 设置", "settingsButton")
        self.themeButton = QPushButton(self.toolbar)
        self.themeButton.setObjectName("themeButton")
        self.themeButton.setCheckable(True)
        self.themeButton.setChecked(self._dark_mode)
        self.toolbar.addWidget(self.themeButton)
        self.languageLabel = QLabel(self.toolbar)
        self.languageLabel.setObjectName("languageLabel")
        self.toolbar.addWidget(self.languageLabel)
        self.languageCombo = QComboBox(self.toolbar)
        self.languageCombo.setObjectName("languageCombo")
        for code in LANGUAGE_CODES:
            self.languageCombo.addItem(LANGUAGE_LABELS[code], code)
        self.languageCombo.setCurrentIndex(max(0, self.languageCombo.findData(self._language)))
        self.toolbar.addWidget(self.languageCombo)
        self._update_theme_button()

    def _toolbar_button(self, text: str, object_name: str) -> QPushButton:
        button = QPushButton(text, self.toolbar)
        button.setObjectName(object_name)
        icon_name = {
            "openButton": "open",
            "analyzeButton": "analyze",
            "exportButton": "export",
            "settingsButton": "settings",
        }.get(object_name)
        if icon_name:
            button.setIcon(icon_for(icon_name, self._theme_tokens))
        self.toolbar.addWidget(button)
        return button

    def _update_theme_button(self) -> None:
        self.themeButton.setText(tr("switch_light", self._language) if self._dark_mode else tr("switch_dark", self._language))
        self.themeButton.setToolTip(
            tr("switch_light", self._language)
            if self._dark_mode
            else tr("switch_dark", self._language)
        )

    @Slot(int)
    def _on_language_changed(self, index: int) -> None:
        code = self.languageCombo.itemData(index)
        if code not in LANGUAGE_CODES:
            return
        self._language = str(code)
        self._settings.setValue("ui/language", self._language)
        self._retranslate_ui()

    def _t(self, key: str, **values: object) -> str:
        return tr(key, self._language, **values)

    def _retranslate_ui(self) -> None:
        """Update GUI chrome without translating protocol abbreviations/data."""

        self.setWindowTitle(self._t("app_title"))
        self.brandLabel.setText(self._t("brand"))
        self.openButton.setText(self._t("open"))
        self.analyzeButton.setText(self._t("analyze"))
        self.exportButton.setText(self._t("export"))
        self.settingsButton.setText(self._t("settings"))
        self.languageLabel.setText(self._t("language"))
        self.conversationHeading.setText(self._t("conversations"))
        self.frameHeading.setText(self._t("can_frames"))
        self.findingHeading.setText(self._t("findings"))
        self.filterLabel.setText(self._t("filter"))
        self.frameSearch.setPlaceholderText(self._t("search_placeholder"))
        self.directionOtherCheck.setText(self._t("other"))
        self.directionFunctionalCheck.setText(self._t("functional"))
        self.showCfCheck.setText(self._t("show_cf"))
        self.highlightDirectionCheck.setText(self._t("color_direction"))
        self.dataLegendLabel.setText(self._t("data_legend"))
        self.emptyCenterLabel.setText(
            self._t("loading")
            if self._state == "LOADING"
            else self._t("analyzing")
            if self._state == "ANALYZING"
            else self._t("empty_trace")
        )
        self._update_theme_button()
        if self._bundle is not None:
            self.statusFrameCount.setText(
                self._t("frames_status", count=len(self._bundle.frames))
            )
            self._update_channel_status(self._bundle)
        else:
            self.statusFrameCount.setText(self._t("frames_status", count=0))
            self.statusChannel.setText(self._t("channel_status", channels="—"))
        finding_count = len(self._analysis_result.findings) if self._analysis_result else 0
        self.statusFindingCount.setText(self._t("findings_status", count=finding_count))
        tab_titles = {
            "frameDetailTab": self._t("frame_details"),
            "isotpDetailTab": "ISO-TP",
            "udsDetailTab": "UDS",
            "sessionDetailTab": self._t("session_details"),
            "evidenceDetailTab": self._t("evidence"),
            "workflowDetailTab": self._t("workflow"),
        }
        for index in range(self.detailTabs.count()):
            tab = self.detailTabs.widget(index)
            if tab is not None and tab.objectName() in tab_titles:
                self.detailTabs.setTabText(index, tab_titles[tab.objectName()])
        self.workflowExpandedCheck.setText(
            self._t("collapse_transfer")
            if self.workflowExpandedCheck.isChecked()
            else self._t("expand_transfer")
        )
        if self._analysis_result is None:
            self.findingSummaryLabel.setText(self._t("finding_count", count=0))
            self._set_default_detail_texts()
            self._render_workflow()
        else:
            self._render_findings(self._analysis_result.findings)
            self._update_analysis_assessment(self._analysis_result)
            self._render_workflow()

    def _set_default_detail_texts(self) -> None:
        defaults = {
            "frameDetailTabText": self._t("select_frame"),
            "isotpDetailTabText": self._t("no_isotp"),
            "udsDetailTabText": self._t("no_uds"),
            "sessionDetailTabText": self._t("no_session"),
            "evidenceDetailTabText": self._t("select_evidence"),
        }
        for object_name, value in defaults.items():
            label = self.findChild(QLabel, object_name)
            if label is not None:
                label.setText(value)

    def _update_analysis_assessment(self, result: AnalysisResult) -> None:
        stats = result.report_data.get("input_stats", {}) if isinstance(result.report_data, dict) else {}
        reasons: list[str] = []
        ambiguous_count = int(stats.get("ambiguous_count", 0) or 0)
        unsupported_count = int(stats.get("unsupported_count", 0) or 0)
        completeness = str((stats.get("trace_quality") or {}).get("completeness", "unknown"))
        if ambiguous_count:
            reasons.append(self._t("ambiguous_reason", count=ambiguous_count))
        if unsupported_count:
            reasons.append(self._t("unsupported_reason", count=unsupported_count))
        if completeness not in {"verified", "assumed"}:
            completeness_display = (
                {
                    "unknown": "无法确认",
                    "known_incomplete": "已知不完整",
                }.get(completeness, completeness)
                if self._language == "zh"
                else completeness
            )
            reasons.append(self._t("coverage_reason", value=completeness_display))
        if any(finding.needs_normative_confirmation for finding in result.findings):
            reasons.append(self._t("manual_review"))
        if any(
            finding.detail.get("match_status") == "orphan_negative_response"
            for finding in result.findings
        ):
            reasons.append(self._t("orphan_reason"))
        self._manual_review_reason = " ".join(reasons)
        self.ambiguousLabel.setVisible(bool(reasons))
        self.ambiguousLabel.setText(
            self._t("manual_reason", reason=self._manual_review_reason)
            if reasons
            else ""
        )
        if not result.findings:
            self.findingSummaryLabel.setText(
                self._t("finding_count", count=0) + "\n" + self._t("no_rule_reason")
            )
        elif reasons:
            self.findingSummaryLabel.setText(
                self._t("finding_count", count=len(result.findings))
                + " · "
                + self._t("manual_review")
            )
        else:
            self.findingSummaryLabel.setText(
                self._t("finding_count", count=len(result.findings))
            )

    def _workflow_status(self, status_key: str) -> str:
        return {
            "positive": self._t("positive"),
            "negative": self._t("negative"),
            "no_response": self._t("no_response"),
            "functional": self._t("functional_step"),
        }.get(status_key, status_key)

    def _workflow_addressing(self, value: str) -> str:
        return self._t("functional_addressing") if value == "functional" else self._t("physical")

    def _workflow_description(self, step: dict) -> str:
        """Render protocol fields as a compact, language-aware step description."""

        sid = step.get("sid")
        fields = step.get("fields") or {}
        response_fields = step.get("response_fields") or {}
        if sid is None:
            return str(step.get("detail", "—"))
        parts = [f"0x{int(sid):02X} {step.get('service_name') or 'unknown'}"]
        if step.get("subfunction") is not None:
            parts.append(self._t("subfunction", value=f"0x{int(step['subfunction']):02X}"))
        if step.get("did") is not None:
            parts.append(self._t("did", value=f"0x{int(step['did']):04X}"))
        if sid == 0x34:
            if fields.get("start_address") is not None:
                parts.append(self._t("start_address", value=f"0x{int(fields['start_address']):X}"))
            if fields.get("transfer_length") is not None:
                parts.append(self._t("transfer_length", value=f"0x{int(fields['transfer_length']):X}"))
        elif sid == 0x36:
            if step.get("block_seq") is not None:
                parts.append(self._t("bsc", value=f"0x{int(step['block_seq']):02X}"))
            parts.append(
                self._t(
                    "transfer_bytes",
                    value=fields.get("transfer_data_length", 0),
                )
            )
        elif sid == 0x31:
            if fields.get("routine_id") is not None:
                parts.append(self._t("routine_id", value=f"0x{int(fields['routine_id']):04X}"))
            parts.append(self._t("parameters", value=fields.get("routine_parameters") or "—"))
        elif sid == 0x2E and fields.get("write_data") is not None:
            parts.append(self._t("write_data", value=fields.get("write_data") or "—"))
        elif sid == 0x22 and response_fields.get("read_data") is not None:
            parts.append(self._t("read_data", value=response_fields.get("read_data") or "—"))
        return " · ".join(parts)

    def _collapse_transfer_steps(self, steps: Sequence[dict]) -> list[dict]:
        collapsed: list[dict] = []
        transfer_group: list[dict] = []

        def flush() -> None:
            if not transfer_group:
                return
            first = transfer_group[0]
            last = transfer_group[-1]
            payload_bytes = sum(
                int((item.get("fields") or {}).get("transfer_data_length", 0) or 0)
                for item in transfer_group
            )
            bsc_values = [item.get("block_seq") for item in transfer_group if item.get("block_seq") is not None]
            collapsed.append(
                {
                    **first,
                    "step_label": f"{first.get('step_index', '?')}–{last.get('step_index', '?')}",
                    "ts_end": last.get("ts_end", first.get("ts_start", 0.0)),
                    "status_key": "negative"
                    if any(item.get("status_key") == "negative" for item in transfer_group)
                    else "positive",
                    "detail": (
                        f"0x36 TransferData · count={len(transfer_group)} · "
                        f"payload_bytes={payload_bytes} · "
                        f"BSC={bsc_values[0]:02X}..{bsc_values[-1]:02X}"
                        if bsc_values
                        else f"0x36 TransferData · count={len(transfer_group)} · payload_bytes={payload_bytes}"
                    ),
                    "evidence_frame_refs": tuple(
                        ref
                        for item in (first, last)
                        for ref in item.get("evidence_frame_refs", ())
                    ),
                }
            )
            transfer_group.clear()

        for step in steps:
            if step.get("sid") == 0x36:
                transfer_group.append(step)
            else:
                flush()
                collapsed.append(step)
        flush()
        return collapsed

    @Slot(int)
    def _render_workflow(self, _state: int | None = None) -> None:
        if not hasattr(self, "workflowDetailTable"):
            return
        steps = self._workflow_steps
        if not steps:
            self.workflowDetailTable.setRowCount(0)
            self.workflowDetailTable.setVisible(False)
            self.workflowEmptyLabel.setText(self._t("workflow_empty"))
            self.workflowEmptyLabel.setVisible(True)
            return
        displayed = steps if self.workflowExpandedCheck.isChecked() else self._collapse_transfer_steps(steps)
        self.workflowEmptyLabel.setVisible(False)
        self.workflowDetailTable.setVisible(True)
        self.workflowDetailTable.setRowCount(len(displayed))
        for row, step in enumerate(displayed):
            step_label = step.get("step_label", step.get("step_index", 0))
            status = self._workflow_status(str(step.get("status_key", "")))
            addressing = self._workflow_addressing(str(step.get("addressing", "physical")))
            service = (
                f"0x{int(step['sid']):02X} {step.get('service_name') or 'unknown'}"
                if step.get("sid") is not None
                else "—"
            )
            refs = ", ".join(str(ref) for ref in step.get("evidence_frame_refs", ())) or "—"
            values = (
                str(step_label),
                f"{float(step.get('ts_start', 0.0)):.6f}",
                addressing,
                service,
                self._workflow_description(step),
                status,
                refs,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                self.workflowDetailTable.setItem(row, column, item)
            self.workflowDetailTable.resizeRowToContents(row)

    @Slot()
    def _toggle_theme(self) -> None:
        self._dark_mode = not self._dark_mode
        self._theme_tokens = DARK_TOKENS if self._dark_mode else LIGHT_TOKENS
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._theme_tokens)
        self._update_theme_button()
        self.brandIcon.setPixmap(icon_for("flashreport", self._theme_tokens).pixmap(20, 20))
        for button, icon_name in (
            (self.openButton, "open"),
            (self.analyzeButton, "analyze"),
            (self.exportButton, "export"),
            (self.settingsButton, "settings"),
        ):
            button.setIcon(icon_for(icon_name, self._theme_tokens))
        self.frameModel.set_direction_highlighting(
            self.highlightDirectionCheck.isChecked(), dark_mode=self._dark_mode
        )
        self.frameDelegate.set_dark_mode(self._dark_mode)
        self._settings.setValue("ui/dark_mode", self._dark_mode)

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

        conversation_panel = QWidget(main_splitter)
        conversation_panel.setObjectName("conversationPanel")
        conversation_layout = QVBoxLayout(conversation_panel)
        conversation_layout.setContentsMargins(0, 0, 0, 0)
        conversation_layout.setSpacing(4)
        self.conversationHeading = QLabel(conversation_panel)
        conversation_heading = self.conversationHeading
        conversation_heading.setObjectName("panelHeading")
        conversation_layout.addWidget(conversation_heading)
        self.conversationTree = QTreeView(conversation_panel)
        self.conversationTree.setObjectName("conversationTree")
        self.conversationTree.setModel(self.conversationModel)
        self.conversationTree.setHeaderHidden(True)
        self.conversationTree.setUniformRowHeights(True)
        self.conversationTree.setMinimumWidth(190)
        self.conversationTree.setMaximumWidth(340)
        conversation_layout.addWidget(self.conversationTree)

        frame_panel = QWidget(main_splitter)
        frame_panel.setObjectName("framePanel")
        frame_layout = QVBoxLayout(frame_panel)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(4)
        self.frameHeading = QLabel(frame_panel)
        frame_heading = self.frameHeading
        frame_heading.setObjectName("panelHeading")
        frame_layout.addWidget(frame_heading)
        self._build_frame_filter_bar(frame_panel, frame_layout)
        self.frameTable = QTableView(frame_panel)
        self.frameTable.setObjectName("frameTable")
        self.frameTable.setModel(self.frameProxyModel)
        self.frameTable.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.frameTable.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.frameTable.setAlternatingRowColors(True)
        self.frameTable.setSortingEnabled(True)
        self.frameTable.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.frameTable.setWordWrap(False)
        self.frameTable.verticalHeader().setVisible(False)
        self.frameTable.horizontalHeader().setStretchLastSection(False)
        self.frameTable.setMinimumWidth(520)
        self.frameTable.setToolTip(
            "Data colors: PCI / SID / Subservice / DID or payload\n"
            "数据色块：PCI / 服务号 / 子服务号 / DID 或数据"
        )
        self.frameDelegate = FrameTableDelegate(self.frameTable)
        self.frameDelegate.set_dark_mode(self._dark_mode)
        self.frameTable.setItemDelegate(self.frameDelegate)
        self._configure_frame_columns()
        self.emptyCenterLabel = QLabel(frame_panel)
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

        finding_panel = QWidget(main_splitter)
        finding_panel.setObjectName("findingPanel")
        finding_panel_layout = QVBoxLayout(finding_panel)
        finding_panel_layout.setContentsMargins(0, 0, 0, 0)
        finding_panel_layout.setSpacing(4)
        self.findingHeading = QLabel(finding_panel)
        finding_heading = self.findingHeading
        finding_heading.setObjectName("panelHeading")
        finding_panel_layout.addWidget(finding_heading)
        self.findingSummaryLabel = QLabel("No findings / 未发现", finding_panel)
        self.findingSummaryLabel.setObjectName("findingSummary")
        self.findingSummaryLabel.setWordWrap(True)
        finding_panel_layout.addWidget(self.findingSummaryLabel)
        self.ambiguousLabel = QLabel("AMBIGUOUS / 需人工复核", finding_panel)
        self.ambiguousLabel.setObjectName("ambiguousBadge")
        self.ambiguousLabel.setWordWrap(True)
        self.ambiguousLabel.setVisible(False)
        finding_panel_layout.addWidget(self.ambiguousLabel)

        self.findingList = QScrollArea(finding_panel)
        self.findingList.setObjectName("findingList")
        self.findingList.setWidgetResizable(True)
        self.findingList.setMinimumWidth(300)
        self.findingList.setMaximumWidth(380)
        finding_panel_layout.addWidget(self.findingList)
        self.findingListWidget = QWidget()
        self.findingListWidget.setObjectName("findingListWidget")
        self.findingListLayout = QVBoxLayout(self.findingListWidget)
        self.findingListLayout.setContentsMargins(8, 8, 8, 8)
        self.findingListLayout.setSpacing(8)
        self.findingListLayout.addStretch(1)
        self.findingList.setWidget(self.findingListWidget)
        self.findingListView = QListView(self.findingListWidget)
        self.findingListView.setObjectName("findingListView")
        self.findingListView.setModel(self.findingModel)
        self.findingListView.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.findingListView.setAlternatingRowColors(True)
        self.findingListView.setUniformItemSizes(True)
        self.findingListView.setWordWrap(False)
        self.findingListView.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.findingListView.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.findingListView.setVisible(False)
        finding_selection = self.findingListView.selectionModel()
        if finding_selection is not None:
            finding_selection.currentChanged.connect(self._on_finding_selected)

        main_splitter.setSizes([210, 930, 300])
        root_splitter.addWidget(main_splitter)

        self.detailTabs = QTabWidget(root_splitter)
        self.detailTabs.setObjectName("detailTabs")
        self.detailTabs.setMinimumHeight(180)
        self.detailTabs.setMaximumHeight(350)
        self._add_detail_tab("frameDetailTab", "", "")
        self._add_detail_tab("isotpDetailTab", "ISO-TP", "")
        self._add_detail_tab("udsDetailTab", "UDS", "")
        self._add_detail_tab("sessionDetailTab", "", "")
        self._add_detail_tab("evidenceDetailTab", "", "")
        workflow_tab = QWidget(self.detailTabs)
        workflow_tab.setObjectName("workflowDetailTab")
        self.workflowDetailTab = workflow_tab
        workflow_layout = QVBoxLayout(workflow_tab)
        self.workflowExpandedCheck = QCheckBox(workflow_tab)
        self.workflowExpandedCheck.setObjectName("workflowExpandedCheck")
        workflow_layout.addWidget(self.workflowExpandedCheck)
        self.workflowEmptyLabel = QLabel(workflow_tab)
        self.workflowEmptyLabel.setObjectName("workflowEmptyLabel")
        self.workflowEmptyLabel.setWordWrap(True)
        self.workflowEmptyLabel.setVisible(False)
        workflow_layout.addWidget(self.workflowEmptyLabel)
        self.workflowDetailTable = QTableWidget(workflow_tab)
        self.workflowDetailTable.setObjectName("workflowDetailTable")
        self.workflowDetailTable.setColumnCount(len(WORKFLOW_COLUMNS))
        self.workflowDetailTable.setHorizontalHeaderLabels(WORKFLOW_COLUMNS)
        self.workflowDetailTable.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.workflowDetailTable.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.workflowDetailTable.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.workflowDetailTable.setWordWrap(True)
        self.workflowDetailTable.setAlternatingRowColors(True)
        self.workflowDetailTable.verticalHeader().setVisible(False)
        workflow_header = self.workflowDetailTable.horizontalHeader()
        workflow_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        workflow_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        workflow_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        workflow_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        workflow_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        workflow_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        workflow_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.workflowDetailTable.setSortingEnabled(False)
        workflow_layout.addWidget(self.workflowDetailTable)
        self.workflowExpandedCheck.stateChanged.connect(self._render_workflow)
        self.detailTabs.addTab(workflow_tab, "")
        root_splitter.setSizes([620, 240])
        self._rootSplitter = root_splitter
        self.setCentralWidget(root_splitter)

        selection = self.frameTable.selectionModel()
        if selection is not None:
            selection.currentChanged.connect(self._show_selected_frame)

    def _build_frame_filter_bar(self, parent: QWidget, layout: QVBoxLayout) -> None:
        bar = QWidget(parent)
        self.frameFilterBar = bar
        bar.setObjectName("frameFilterBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 0, 4, 2)
        bar_layout.setSpacing(6)
        self.filterLabel = QLabel(bar)
        self.filterLabel.setObjectName("filterLabel")
        bar_layout.addWidget(self.filterLabel)
        self.frameSearch = QLineEdit(bar)
        self.frameSearch.setObjectName("frameSearch")
        self.frameSearch.setPlaceholderText("Search CAN ID / Data / UDS…")
        self.frameSearch.setClearButtonEnabled(True)
        self.frameSearch.setToolTip("Search all visible columns / 搜索所有可见列")
        self.frameSearch.setMinimumWidth(150)
        bar_layout.addWidget(self.frameSearch, 1)
        self.directionTesterCheck = QCheckBox("T→E", bar)
        self.directionTesterCheck.setObjectName("directionTesterCheck")
        self.directionTesterCheck.setToolTip("Tester to ECU / 测试仪到 ECU")
        self.directionEcuCheck = QCheckBox("E→T", bar)
        self.directionEcuCheck.setObjectName("directionEcuCheck")
        self.directionEcuCheck.setToolTip("ECU to Tester / ECU 到测试仪")
        self.directionOtherCheck = QCheckBox("Other", bar)
        self.directionOtherCheck.setObjectName("directionOtherCheck")
        self.directionOtherCheck.setToolTip("Unclassified direction / 未归类方向")
        for checkbox in (
            self.directionTesterCheck,
            self.directionEcuCheck,
            self.directionOtherCheck,
        ):
            checkbox.setChecked(True)
            bar_layout.addWidget(checkbox)
        self.directionFunctionalCheck = QCheckBox("Func", bar)
        self.directionFunctionalCheck.setObjectName("directionFunctionalCheck")
        self.directionFunctionalCheck.setChecked(True)
        self.directionFunctionalCheck.setToolTip("Functional addressing / 功能寻址")
        bar_layout.addWidget(self.directionFunctionalCheck)
        self.showCfCheck = QCheckBox("Show CF", bar)
        self.showCfCheck.setObjectName("showCfCheck")
        self.showCfCheck.setChecked(True)
        self.showCfCheck.setToolTip("Include consecutive frames / 显示连续帧 CF")
        bar_layout.addWidget(self.showCfCheck)
        self.highlightDirectionCheck = QCheckBox("Color direction", bar)
        self.highlightDirectionCheck.setObjectName("highlightDirectionCheck")
        self.highlightDirectionCheck.setToolTip(
            "Color T→E and E→T rows differently / 用不同底色区分 T→E 与 E→T"
        )
        bar_layout.addWidget(self.highlightDirectionCheck)
        self.dataLegendLabel = QLabel("PCI · SID · Sub · DID", bar)
        self.dataLegendLabel.setObjectName("dataLegend")
        self.dataLegendLabel.setToolTip(
            "Data byte colors / 数据字节颜色：PCI、服务号、子服务号、DID/数据"
        )
        bar_layout.addWidget(self.dataLegendLabel)
        layout.addWidget(bar)
        self.frameSearch.textChanged.connect(self.frameProxyModel.set_query)
        for checkbox in (
            self.directionTesterCheck,
            self.directionEcuCheck,
            self.directionOtherCheck,
            self.directionFunctionalCheck,
            self.showCfCheck,
        ):
            checkbox.stateChanged.connect(self._apply_frame_filters)
        self.highlightDirectionCheck.stateChanged.connect(self._apply_direction_highlighting)

    def _configure_frame_columns(self) -> None:
        header = self.frameTable.horizontalHeader()
        widths = {
            0: 48,   # row number / 序号
            1: 125,  # timestamp / 时间
            2: 92,   # delta / 间隔
            3: 42,   # CH
            4: 90,   # CAN ID
            5: 100,  # direction / 方向
            6: 40,   # DLC
            7: 230,  # data / 数据
            8: 150,  # ISO-TP
            9: 230,  # UDS
            10: 0,   # Summary retained for compatibility but hidden / 兼容保留但隐藏
        }
        for section, width in widths.items():
            if section == 10:
                self.frameTable.setColumnHidden(section, True)
                continue
            header.setSectionResizeMode(section, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(section, width)
        header.setMinimumSectionSize(32)

    @Slot()
    def _apply_frame_filters(self) -> None:
        directions = {
            direction
            for direction, checkbox in (
                ("tester->ecu", self.directionTesterCheck),
                ("ecu->tester", self.directionEcuCheck),
                ("other", self.directionOtherCheck),
                ("functional", self.directionFunctionalCheck),
            )
            if checkbox.isChecked()
        }
        self.frameProxyModel.set_allowed_directions(directions)
        self.frameProxyModel.set_hide_cf(not self.showCfCheck.isChecked())

    @Slot()
    def _apply_direction_highlighting(self) -> None:
        self.frameModel.set_direction_highlighting(
            self.highlightDirectionCheck.isChecked(), dark_mode=self._dark_mode
        )

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
        self.statusFrameCount = QLabel(status)
        self.statusFrameCount.setObjectName("statusFrameCount")
        self.statusFindingCount = QLabel(status)
        self.statusFindingCount.setObjectName("statusFindingCount")
        self.statusState = QLabel("EMPTY", status)
        self.statusState.setObjectName("statusState")
        self.statusChannel = QLabel(status)
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
        self.statusState.setProperty("state", state)
        self.statusState.style().unpolish(self.statusState)
        self.statusState.style().polish(self.statusState)
        self.openButton.setEnabled(state not in {"LOADING", "ANALYZING"})
        self.analyzeButton.setEnabled(has_bundle and state in {"READY", "RESULT"})
        self.exportButton.setEnabled(state == "RESULT" and self._analysis_result is not None)
        self.settingsButton.setEnabled(state not in {"LOADING", "ANALYZING"})
        self.emptyCenterLabel.setVisible(state in {"EMPTY", "LOADING", "ANALYZING"})
        self.errorLabel.setVisible(state == "ERROR")
        self.frameHeading.setVisible(state != "EMPTY")
        self.frameFilterBar.setVisible(state in {"READY", "RESULT"})
        self.frameTable.setVisible(state not in {"EMPTY", "ERROR", "LOADING"})
        if state != "RESULT":
            self.ambiguousLabel.setVisible(False)
        return True

    def set_bundle(self, bundle: TraceBundle) -> None:
        """Project a loaded API bundle into the frozen UI / 将 API bundle 投影到界面。"""

        self._bundle = bundle
        self._analysis_result = None
        self._workflow_steps = []
        self.frameModel.set_data(bundle.frames, bundle.frame_annotations, bundle.quality.start_ts)
        self.conversationModel.set_summaries(bundle.conversation_summaries)
        self.findingModel.set_findings(())
        self._render_findings(())
        self._render_workflow()
        self.statusFrameCount.setText(tr("frames_status", self._language, count=len(bundle.frames)))
        self.statusFindingCount.setText(tr("findings_status", self._language, count=0))
        self._update_channel_status(bundle)
        self.ambiguousLabel.setVisible(False)
        self.set_state("READY", force=True)

    def set_analysis_result(self, result: AnalysisResult) -> None:
        """Project analysis output and render evidence cards / 展示分析结果和证据卡片。"""

        self._analysis_result = result
        self._bundle = result.bundle
        self._workflow_steps = list(result.workflow_steps or result.report_data.get("workflow", []))
        annotations = result.frame_annotations or result.bundle.frame_annotations
        self.frameModel.set_data(result.bundle.frames, annotations, result.bundle.quality.start_ts)
        self.conversationModel.set_summaries(result.conversation_summaries or result.bundle.conversation_summaries)
        self.findingModel.set_findings(result.findings)
        self._render_findings(result.findings)
        self.statusFrameCount.setText(tr("frames_status", self._language, count=len(result.bundle.frames)))
        self.statusFindingCount.setText(tr("findings_status", self._language, count=len(result.findings)))
        self._update_channel_status(result.bundle)
        input_stats = result.report_data.get("input_stats", {}) if isinstance(result.report_data, dict) else {}
        self.ambiguousLabel.setVisible(bool(input_stats.get("ambiguous")))
        self._update_analysis_assessment(result)
        self._render_workflow()
        self.set_state("RESULT", force=True)

    # ---------- asynchronous interaction / 异步交互 ----------
    def _open_file_dialog(self) -> None:
        start = self._settings.value("ui/last_open_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("open_dialog"),
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
        self._workflow_steps = []
        self.frameModel.set_data((), {}, 0.0)
        self.conversationModel.set_summaries(())
        self.findingModel.set_findings(())
        self._render_findings(())
        self._render_workflow()
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
            self._t("export_dialog"),
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
        dialog = ConfigDialog(self._config, self._settings, self._language, self)
        dialog.configSaved.connect(self._on_config_saved)
        dialog.exec()

    @Slot(object)
    def _on_config_saved(self, config: AppConfig) -> None:
        self._config = config
        self.statusBar().showMessage("Configuration updated" if self._language == "en" else "配置已更新", 4000)

    @Slot()
    def _on_load_started(self) -> None:
        self._begin_busy_interval()
        self.emptyCenterLabel.setText(self._t("loading"))
        self.set_state("LOADING")
        self.loadStarted.emit()

    @Slot(object)
    def _on_load_finished(self, bundle: object) -> None:
        if not isinstance(bundle, TraceBundle):
            self._show_error(self._t("invalid_load"))
            return
        self.set_bundle(bundle)
        if self._active_path:
            self._settings.setValue("ui/last_open_dir", str(Path(self._active_path).parent))
        self.statusBar().showMessage(self._t("trace_loaded"), 4000)
        self.loadFinished.emit(bundle)

    @Slot(str)
    def _on_load_failed(self, message: str) -> None:
        self._show_error(self._t("load_error", message=message))
        self.loadFailed.emit(message)

    @Slot()
    def _on_analysis_started(self) -> None:
        self._begin_busy_interval()
        self.emptyCenterLabel.setText(self._t("analyzing"))
        self.set_state("ANALYZING")
        self.analysisStarted.emit()

    @Slot(object)
    def _on_analysis_finished(self, result: object) -> None:
        if not isinstance(result, AnalysisResult):
            self._show_error(self._t("invalid_analysis"))
            return
        self.set_analysis_result(result)
        self.statusBar().showMessage(self._t("analysis_completed"), 4000)
        self.analysisFinished.emit(result)

    @Slot(str)
    def _on_analysis_failed(self, message: str) -> None:
        self._show_error(self._t("analysis_error", message=message))
        self.analysisFailed.emit(message)

    @Slot()
    def _on_export_started(self) -> None:
        self._begin_busy_interval()
        self._exporting = True
        self.openButton.setEnabled(False)
        self.analyzeButton.setEnabled(False)
        self.exportButton.setEnabled(False)
        self.statusBar().showMessage(self._t("exporting"))
        self.exportStarted.emit()

    @Slot(object)
    def _on_export_finished(self, value: object) -> None:
        self._exporting = False
        self.set_state("RESULT")
        self.statusBar().showMessage(self._t("exported"), 5000)
        self.exportFinished.emit(value)

    @Slot(str)
    def _on_export_failed(self, message: str) -> None:
        self._exporting = False
        self._show_error(self._t("export_error", message=message))
        self.exportFailed.emit(message)

    def _show_error(self, message: str) -> None:
        self._last_error_message = message
        self._workflow_steps = []
        self.errorLabel.setText(message)
        self.ambiguousLabel.setVisible(False)
        self.findingModel.set_findings(())
        self._render_findings(())
        self._render_workflow()
        self.set_state("ERROR", force=True)

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
        self.statusChannel.setText(tr("channel_status", self._language, channels=channels))

    def _clear_finding_cards(self) -> None:
        while self.findingListLayout.count():
            item = self.findingListLayout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if widget is self.findingListView:
                    widget.hide()
                else:
                    widget.deleteLater()

    def _render_findings(self, findings: Sequence[Finding]) -> None:
        self._clear_finding_cards()
        self.findingSummaryLabel.setText(
            self._t("finding_count", count=f"{len(findings):,}")
            if findings
            else self._t("finding_count", count=0)
        )
        if not findings:
            empty = QLabel(self._t("no_findings"), self.findingListWidget)
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            self.findingListLayout.addWidget(empty)
            self.findingListLayout.addStretch(1)
            return
        if len(findings) > self._finding_card_limit:
            self.findingSummaryLabel.setText(self._t("finding_focus", count=f"{len(findings):,}"))
            self.findingListLayout.addWidget(self.findingListView)
            self.findingListView.show()
            self.findingListView.setCurrentIndex(self.findingModel.index(-1, 0))
            return
        for finding in findings:
            self.findingListLayout.addWidget(self._finding_card(finding))
        self.findingListLayout.addStretch(1)

    def _finding_card(self, finding: Finding) -> QFrame:
        card = QFrame(self.findingListWidget)
        card.setObjectName(f"findingCard_{finding.finding_id}")
        card.setProperty("severity", finding.confidence.lower())
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        title = QLabel(self._t("finding_title", id=finding.finding_id, layer=finding.layer), card)
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)
        meta = QLabel(
            f"{self._t('confidence', value=finding.confidence)} · "
            f"{self._t('side', value=finding.suspected_side)} · "
            f"{self._t('deviation', value=finding.deviation_ts)}",
            card,
        )
        meta.setObjectName("secondaryText")
        meta.setWordWrap(True)
        layout.addWidget(meta)
        observed = QLabel(
            f"{self._t('observed', value=finding.observed)}\n"
            f"{self._t('expected', value=finding.expected)}",
            card,
        )
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
        summary_text = getattr(evidence, "summary", self._t("evidence"))
        if getattr(evidence, "type", None) == "frame":
            summary_text += "\n" + self._t(
                "frame_line",
                line=getattr(evidence, "line_no", "?"),
                time=float(getattr(evidence, "ts", 0.0)),
                can_id=f"{getattr(evidence, 'can_id', 0):X}",
            )
        elif getattr(evidence, "type", None) == "absence_window":
            summary_text += "\n" + self._t(
                "interval",
                start=float(getattr(evidence, "ts_start", 0.0)),
                end=float(getattr(evidence, "ts_end", 0.0)),
                count=int(getattr(evidence, "matched_frame_count", 0)),
            )
        summary = QLabel(summary_text, row)
        summary.setWordWrap(True)
        row_layout.addWidget(summary, 1)
        button = QPushButton(row)
        if getattr(evidence, "type", None) == "frame":
            button.setText(self._t("jump"))
            button.setObjectName(f"evidenceJump_{finding.finding_id}_{index}")
            button.clicked.connect(
                lambda _checked=False, item=evidence: self.jump_to_frame(item, finding=finding)
            )
        else:
            button.setText(self._t("show"))
            button.setObjectName(f"evidenceShow_{finding.finding_id}_{index}")
            button.clicked.connect(
                lambda _checked=False, item=evidence: self.show_interval(item, finding=finding)
            )
        button.setEnabled(True)
        row_layout.addWidget(button)
        layout.addWidget(row)

    def _reset_frame_filters_for_focus(self) -> None:
        """Reveal evidence rows even when the current filter hides them."""

        self.frameSearch.clear()
        self.directionTesterCheck.setChecked(True)
        self.directionEcuCheck.setChecked(True)
        self.directionOtherCheck.setChecked(True)
        self.directionFunctionalCheck.setChecked(True)
        self.showCfCheck.setChecked(True)
        self.statusBar().showMessage(
            self._t("evidence") + " · " + self._t("show"), 4000
        )

    def _set_finding_evidence_detail(self, finding: Finding, evidence: object) -> None:
        detail = self.findChild(QLabel, "evidenceDetailTabText")
        if detail is None:
            return
        evidence_type = getattr(evidence, "type", "evidence")
        location = (
            self._t("location_frame", value=getattr(evidence, "frame_ref", "unknown"))
            if evidence_type == "frame"
            else self._t(
                "location_interval",
                value=float(getattr(evidence, "ts_start", 0.0)),
                value_end=float(getattr(evidence, "ts_end", 0.0)),
            )
        )
        detail.setText(
            f"{self._t('finding_context', id=finding.finding_id)} ({finding.layer})\n"
            f"{self._t('confidence', value=finding.confidence)} · "
            f"{self._t('side', value=finding.suspected_side)}\n"
            f"{self._t('deviation', value=finding.deviation_ts)}\n"
            f"{self._t('observed', value=finding.observed)}\n"
            f"{self._t('expected', value=finding.expected)}\n"
            f"{location}\n"
            f"{self._t('evidence')}: {getattr(evidence, 'summary', '')}"
        )

    def jump_to_frame(self, evidence: object, *, finding: Finding | None = None) -> bool:
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
            self._reset_frame_filters_for_focus()
            proxy_index = self.frameProxyModel.mapFromSource(source_index)
        if not proxy_index.isValid():
            return False
        selection = self.frameTable.selectionModel()
        if selection is not None:
            selection.clearSelection()
            selection.select(proxy_index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.frameTable.setCurrentIndex(proxy_index)
        self.frameTable.scrollTo(proxy_index, QTableView.ScrollHint.PositionAtCenter)
        if finding is not None:
            self._set_finding_evidence_detail(finding, evidence)
            self.detailTabs.setCurrentWidget(self.evidenceDetailTab)
        else:
            self.detailTabs.setCurrentWidget(self.frameDetailTab)
        return True

    def show_interval(self, evidence: object, *, finding: Finding | None = None) -> bool:
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
            first = self.frameProxyModel.mapFromSource(self.frameModel.index(matching_rows[0], 0)) if matching_rows else None
            last = self.frameProxyModel.mapFromSource(self.frameModel.index(matching_rows[-1], 0)) if matching_rows else None
            if first is None or not first.isValid() or last is None or not last.isValid():
                self._reset_frame_filters_for_focus()
                first = self.frameProxyModel.mapFromSource(self.frameModel.index(matching_rows[0], 0)) if matching_rows else None
                last = self.frameProxyModel.mapFromSource(self.frameModel.index(matching_rows[-1], 0)) if matching_rows else None
            if first is not None and first.isValid() and last is not None and last.isValid():
                selection.select(
                    QItemSelection(first, last),
                    QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                )
            if matching_rows:
                if first is not None and first.isValid():
                    self.frameTable.setCurrentIndex(first)
                    self.frameTable.scrollTo(first, QTableView.ScrollHint.PositionAtCenter)
                if last is not None and last.isValid():
                    self.frameTable.scrollTo(last, QTableView.ScrollHint.PositionAtCenter)
        detail = self.findChild(QLabel, "evidenceDetailTabText")
        if detail is not None:
            detail.setText(
                f"{self._t('finding_context', id=getattr(finding, 'finding_id', 'evidence'))}\n"
                f"{self._t('observed', value=getattr(finding, 'observed', ''))}\n"
                f"{self._t('expected', value=getattr(finding, 'expected', ''))}\n"
                f"{self._t('location_interval', value=start, value_end=end)}\n"
                f"{self._t('expected_role', value=getattr(evidence, 'expected_role', 'unknown'))}\n"
                f"{self._t('expected_kind', value=getattr(evidence, 'expected_kind', 'unknown'))}\n"
                f"{self._t('matched_frames', value=getattr(evidence, 'matched_frame_count', len(matching_rows)))}\n"
                f"{self._t('coverage', value=getattr(evidence, 'trace_coverage_ok', None))}\n"
                f"{getattr(evidence, 'summary', '')}"
            )
        self.detailTabs.setCurrentWidget(self.evidenceDetailTab)
        return True

    @Slot(object, object)
    def _on_finding_selected(self, current: object, previous: object) -> None:
        del previous
        if not hasattr(current, "isValid") or not current.isValid():
            return
        finding = current.data(FindingRole)
        if not isinstance(finding, Finding) or not finding.evidence:
            return
        evidence = finding.evidence[0]
        if getattr(evidence, "type", None) == "frame":
            self.jump_to_frame(evidence, finding=finding)
        else:
            self.show_interval(evidence, finding=finding)

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
        data_hex = " ".join(f"{byte:02X}" for byte in frame.data)
        direction = getattr(annotation, "direction", "other")
        isotp_summary = getattr(annotation, "isotp_summary", "") or "—"
        uds_summary = getattr(annotation, "uds_summary", "") or "—"
        addressing = getattr(annotation, "addressing_mode", "unknown")
        uds_details = getattr(annotation, "uds_details", {}) or {}
        detail_lines = [
            self._t("service", value=uds_details.get("service_name") or "—"),
            self._t("subfunction", value=(
                f"0x{uds_details['subfunction']:02X}"
                if uds_details.get("subfunction") is not None
                else "—"
            )),
            self._t("did", value=(
                f"0x{uds_details['did']:04X}"
                if uds_details.get("did") is not None
                else "—"
            )),
            self._t("bsc", value=(
                f"0x{uds_details['block_seq']:02X}"
                if uds_details.get("block_seq") is not None
                else "—"
            )),
            self._t("nrc", value=(
                f"0x{uds_details['nrc']:02X} ({uds_details.get('nrc_name') or 'unknownNRC'})"
                if uds_details.get("nrc") is not None
                else "—"
            )),
            self._t("session", value=uds_details.get("session") or "—"),
        ]
        if uds_details.get("read_data") is not None:
            detail_lines.append(self._t("read_data", value=uds_details["read_data"] or "—"))
        if uds_details.get("write_data") is not None:
            detail_lines.append(self._t("write_data", value=uds_details["write_data"] or "—"))
        if uds_details.get("start_address") is not None:
            detail_lines.append(
                self._t("start_address", value=f"0x{uds_details['start_address']:X}")
            )
        if uds_details.get("transfer_length") is not None:
            detail_lines.append(
                self._t("transfer_length", value=f"0x{uds_details['transfer_length']:X}")
            )
        if uds_details.get("routine_id") is not None:
            detail_lines.append(
                self._t("routine_id", value=f"0x{uds_details['routine_id']:04X}")
            )
            detail_lines.append(
                self._t("parameters", value=uds_details.get("routine_parameters") or "—")
            )
        detail.setText(
            f"{self._t('frame', value=frame.frame_ref)}\n"
            f"{self._t('time', value=f'{frame.ts_display} ({frame.ts_seconds:.6f}s)')}\n"
            f"{self._t('channel', value=frame.channel if frame.channel is not None else '—')}\n"
            f"{self._t('can_id', value=f'{frame.can_id:X}')}\n"
            f"{self._t('dlc', value=frame.dlc)}\n"
            f"{self._t('data', value=data_hex)}\n"
            f"{self._t('direction', value=direction)}\n"
            f"{self._t('addressing', value=addressing)}\n"
            f"{self._t('isotp', value=isotp_summary)}\n"
            f"{self._t('uds', value=uds_summary)}\n"
            + "\n".join(detail_lines)
        )
        isotp_label = self.findChild(QLabel, "isotpDetailTabText")
        if isotp_label is not None:
            isotp_label.setText(
                f"{self._t('frame', value=frame.frame_ref)}\n"
                f"{self._t('isotp', value=isotp_summary)}\n"
                f"{self._t('direction', value=direction)}\n"
                f"{self._t('addressing', value=addressing)}\n"
                f"{self._t('data_label', value=data_hex)}"
            )
        uds_label = self.findChild(QLabel, "udsDetailTabText")
        if uds_label is not None:
            uds_label.setText(
                f"{self._t('frame', value=frame.frame_ref)}\n"
                f"{self._t('uds', value=uds_summary)}\n"
                + "\n".join(detail_lines)
                + f"\n{self._t('raw_uds', value=uds_details.get('raw') or '—')}"
            )
        session_label = self.findChild(QLabel, "sessionDetailTabText")
        if session_label is not None:
            session_label.setText(
                f"{self._t('session', value=uds_details.get('session') or '—')}\n"
                f"{self._t('addressing', value=addressing)}\n"
                f"{self._t('direction', value=direction)}"
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
