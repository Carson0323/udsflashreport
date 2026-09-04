"""Async report export controller / 异步报告导出控制器。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThreadPool, Qt, Signal, Slot

import flashreport_core.api as api
from flashreport_core.models import AnalysisResult

from .worker import FunctionWorker


class ExportController(QObject):
    """Run Markdown/JSON/schema/disk export through the public API in a worker."""

    exportStarted = Signal()  # noqa: N815
    exportFinished = Signal(object)  # noqa: N815
    exportFailed = Signal(str)  # noqa: N815

    def __init__(self, thread_pool: QThreadPool | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.thread_pool = thread_pool or QThreadPool.globalInstance()
        self._tasks: set[FunctionWorker] = set()

    def export(self, result: AnalysisResult, md_path: str | None, json_path: str | None) -> None:
        self.exportStarted.emit()
        worker = FunctionWorker(lambda: api.export_report(result, md_path, json_path))
        self._tasks.add(worker)
        worker.signals.finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)
        worker.signals.failed.connect(self._on_failed, Qt.ConnectionType.QueuedConnection)
        self.thread_pool.start(worker)

    @Slot(object, object)
    def _on_finished(self, worker: FunctionWorker, value: object) -> None:
        self._tasks.discard(worker)
        self.exportFinished.emit(value)

    @Slot(object, str)
    def _on_failed(self, worker: FunctionWorker, message: str) -> None:
        self._tasks.discard(worker)
        self.exportFailed.emit(message)
