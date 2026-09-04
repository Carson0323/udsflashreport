"""Model/View projection for raw frames / 原始帧的 Model/View 投影。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt

from flashreport_core.models import FrameAnnotation, RawFrame


FRAME_COLUMNS = (
    "#",
    "Time",
    "Δt",
    "Channel",
    "CAN ID",
    "Direction",
    "DLC",
    "Data",
    "ISO-TP",
    "UDS",
    "Summary",
)

_USER_ROLE = int(Qt.ItemDataRole.UserRole)
FRAME_REF_ROLE = _USER_ROLE + 1
FRAME_OBJECT_ROLE = _USER_ROLE + 2
ANNOTATION_ROLE = _USER_ROLE + 3

# Readable aliases are useful for tests and for future view delegates.
FrameRefRole = FRAME_REF_ROLE
FrameObjectRole = FRAME_OBJECT_ROLE
AnnotationRole = ANNOTATION_ROLE


class FrameTableModel(QAbstractTableModel):
    """Expose raw frames and precomputed annotations without protocol inference.

    The model deliberately receives ``FrameAnnotation`` objects from the public
    API. It never decodes CAN/ISO-TP/UDS data itself; the GUI is a projection
    layer only / 模型只展示 API 提供的结果，不在 GUI 内推导协议语义。
    """

    def __init__(
        self,
        frames: Sequence[RawFrame] | None = None,
        annotations: Mapping[str, FrameAnnotation] | None = None,
        start_ts: float | None = None,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._frames = list(frames or ())
        self._annotations = dict(annotations or {})
        self._start_ts = start_ts if start_ts is not None else self._infer_start_ts()

    def _infer_start_ts(self) -> float:
        return self._frames[0].ts_seconds if self._frames else 0.0

    def set_data(
        self,
        frames: Sequence[RawFrame],
        annotations: Mapping[str, FrameAnnotation] | None = None,
        start_ts: float | None = None,
    ) -> None:
        self.beginResetModel()
        self._frames = list(frames)
        self._annotations = dict(annotations or {})
        self._start_ts = start_ts if start_ts is not None else self._infer_start_ts()
        self.endResetModel()

    def set_annotations(self, annotations: Mapping[str, FrameAnnotation]) -> None:
        self.beginResetModel()
        self._annotations = dict(annotations)
        self.endResetModel()

    def frame_at(self, row: int) -> RawFrame | None:
        if 0 <= row < len(self._frames):
            return self._frames[row]
        return None

    def annotation_at(self, row: int) -> FrameAnnotation | None:
        frame = self.frame_at(row)
        return self._annotations.get(frame.frame_ref) if frame is not None else None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._frames)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(FRAME_COLUMNS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(FRAME_COLUMNS):
            return FRAME_COLUMNS[section]
        if orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < len(self._frames)):
            return None
        frame = self._frames[index.row()]
        annotation = self._annotations.get(frame.frame_ref)

        if role == FRAME_REF_ROLE:
            return frame.frame_ref
        if role == FRAME_OBJECT_ROLE:
            return frame
        if role == ANNOTATION_ROLE:
            return annotation
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        column = index.column()
        previous = self._frames[index.row() - 1] if index.row() else None
        if column == 0:
            return str(index.row() + 1)
        if column == 1:
            return f"{frame.ts_seconds - self._start_ts:.6f}"
        if column == 2:
            delta = frame.ts_seconds - previous.ts_seconds if previous is not None else 0.0
            return f"{delta:.6f}"
        if column == 3:
            return "" if frame.channel is None else str(frame.channel)
        if column == 4:
            return f"{frame.can_id:08X}" if frame.is_extended else f"{frame.can_id:03X}"
        if column == 5:
            return annotation.direction if annotation is not None else "other"
        if column == 6:
            return str(frame.dlc)
        if column == 7:
            return " ".join(f"{byte:02X}" for byte in frame.data)
        if column == 8:
            return annotation.isotp_summary if annotation is not None and annotation.isotp_summary else ""
        if column == 9:
            return annotation.uds_summary if annotation is not None and annotation.uds_summary else ""
        if column == 10:
            return annotation.summary if annotation is not None else "other"
        return None


class FrameFilterProxyModel(QSortFilterProxyModel):
    """Case-insensitive whole-row filter for the frame table / 帧表过滤器。"""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)

    def set_query(self, query: str) -> None:
        self.setFilterFixedString(query)
