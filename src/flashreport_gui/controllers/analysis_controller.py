"""Async load/analyze controller / 异步加载与分析控制器。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThreadPool, Qt, Signal, Slot

import flashreport_core.api as api
from flashreport_core.models import AnalysisResult, AppConfig, TraceBundle

from .worker import FunctionWorker


class AnalysisController(QObject):
    """Schedule public API load/analyze calls on a QThreadPool."""

    loadStarted = Signal()  # noqa: N815
    loadFinished = Signal(object)  # noqa: N815
    loadFailed = Signal(str)  # noqa: N815
    analysisStarted = Signal()  # noqa: N815
    analysisFinished = Signal(object)  # noqa: N815
    analysisFailed = Signal(str)  # noqa: N815

    def __init__(self, thread_pool: QThreadPool | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.thread_pool = thread_pool or QThreadPool.globalInstance()
        self._tasks: set[FunctionWorker] = set()

    def _submit(self, function: Callable[[], object], started: Signal, kind: str) -> None:
        started.emit()
        worker = FunctionWorker(function)
        self._tasks.add(worker)
        if kind == "load":
            worker.signals.finished.connect(self._on_load_finished, Qt.ConnectionType.QueuedConnection)
            worker.signals.failed.connect(self._on_load_failed, Qt.ConnectionType.QueuedConnection)
        else:
            worker.signals.finished.connect(self._on_analysis_finished, Qt.ConnectionType.QueuedConnection)
            worker.signals.failed.connect(self._on_analysis_failed, Qt.ConnectionType.QueuedConnection)
        self.thread_pool.start(worker)

    def load_file(self, path: str, config: AppConfig) -> None:
        self._submit(
            lambda: api.load_trace(path, config),
            self.loadStarted,
            "load",
        )

    def analyze(self, bundle: TraceBundle, config: AppConfig) -> None:
        self._submit(
            lambda: api.analyze_trace(bundle, config),
            self.analysisStarted,
            "analysis",
        )

    @Slot(object, object)
    def _on_load_finished(self, worker: FunctionWorker, bundle: object) -> None:
        self._tasks.discard(worker)
        self.loadFinished.emit(bundle)

    @Slot(object, str)
    def _on_load_failed(self, worker: FunctionWorker, message: str) -> None:
        self._tasks.discard(worker)
        self.loadFailed.emit(message)

    @Slot(object, object)
    def _on_analysis_finished(self, worker: FunctionWorker, result: object) -> None:
        self._tasks.discard(worker)
        self.analysisFinished.emit(result)

    @Slot(object, str)
    def _on_analysis_failed(self, worker: FunctionWorker, message: str) -> None:
        self._tasks.discard(worker)
        self.analysisFailed.emit(message)
