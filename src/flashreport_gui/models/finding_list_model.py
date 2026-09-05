"""Finding list projection / Finding 列表投影。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from flashreport_core.models import Finding

from ..i18n import format_finding_text, side_label


FINDING_ROLE = int(Qt.ItemDataRole.UserRole) + 1
FindingRole = FINDING_ROLE


class FindingListModel(QAbstractListModel):
    """Expose findings for selection and future card delegates."""

    def __init__(self, findings: Sequence[Finding] | None = None, parent: object | None = None) -> None:
        super().__init__(parent)
        self._findings = list(findings or ())
        self._language = "en"

    def set_findings(self, findings: Sequence[Finding]) -> None:
        self.beginResetModel()
        self._findings = list(findings)
        self.endResetModel()

    def set_language(self, language: str) -> None:
        language = language if language in {"zh", "en"} else "en"
        if language == self._language:
            return
        self._language = language
        if self.rowCount():
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, 0),
                [Qt.ItemDataRole.DisplayRole],
            )

    def finding_at(self, row: int) -> Finding | None:
        return self._findings[row] if 0 <= row < len(self._findings) else None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._findings)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        finding = self.finding_at(index.row()) if index.isValid() else None
        if finding is None:
            return None
        if role == FINDING_ROLE:
            return finding
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                f"{finding.finding_id} · {finding.layer} · "
                f"t={finding.deviation_ts:.6f}s · "
                f"{side_label(finding.suspected_side, self._language)} · "
                f"{format_finding_text(finding.finding_id, 'observed', finding.observed, self._language, detail=finding.detail, service=finding.service)} → "
                f"{format_finding_text(finding.finding_id, 'expected', finding.expected, self._language, detail=finding.detail, service=finding.service)}"
            )
        return None
