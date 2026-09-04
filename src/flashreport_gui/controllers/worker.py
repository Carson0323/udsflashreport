"""Small QThreadPool worker / QThreadPool 任务封装。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    """Signals emitted by a background task / 后台任务信号。"""

    finished = Signal(object, object)
    failed = Signal(object, str)


class FunctionWorker(QRunnable):
    """Run a callable away from the GUI thread."""

    def __init__(self, function: Callable[[], object]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function()
        except Exception as exc:  # noqa: BLE001 - transport error to GUI
            self.signals.failed.emit(self, f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(self, result)
