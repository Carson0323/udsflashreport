"""Model/View projection for raw frames / 原始帧的 Model/View 投影。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, QSortFilterProxyModel, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem, QStyledItemDelegate

from flashreport_core.models import FrameAnnotation, RawFrame

from ..i18n import direction_label, format_uds_summary


FRAME_COLUMNS = (
    "#",
    "Time",
    "Δt",
    "CH",
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
FRAME_SORT_ROLE = _USER_ROLE + 4

# Readable aliases are useful for tests and for future view delegates.
FrameRefRole = FRAME_REF_ROLE
FrameObjectRole = FRAME_OBJECT_ROLE
AnnotationRole = ANNOTATION_ROLE
FrameSortRole = FRAME_SORT_ROLE


def _chronological(frames: Sequence[RawFrame]) -> list[RawFrame]:
    """Keep the table and Δt calculations in capture chronology."""

    return sorted(frames, key=lambda frame: (frame.ts_seconds, frame.line_no, frame.frame_ref))


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
        self._frames = _chronological(frames or ())
        self._annotations = dict(annotations or {})
        self._start_ts = start_ts if start_ts is not None else self._infer_start_ts()
        self._highlight_directions = False
        self._dark_mode = False
        # Keep the standalone model's historical English default; MainWindow
        # applies the user's selected language immediately after construction.
        self._language = "en"

    def _infer_start_ts(self) -> float:
        return self._frames[0].ts_seconds if self._frames else 0.0

    def set_data(
        self,
        frames: Sequence[RawFrame],
        annotations: Mapping[str, FrameAnnotation] | None = None,
        start_ts: float | None = None,
    ) -> None:
        self.beginResetModel()
        self._frames = _chronological(frames)
        self._annotations = dict(annotations or {})
        self._start_ts = start_ts if start_ts is not None else self._infer_start_ts()
        self.endResetModel()

    def set_annotations(self, annotations: Mapping[str, FrameAnnotation]) -> None:
        self.beginResetModel()
        self._annotations = dict(annotations)
        self.endResetModel()

    def set_language(self, language: str) -> None:
        language = language if language in {"zh", "en"} else "en"
        if language == self._language:
            return
        self._language = language
        if self.rowCount():
            self.dataChanged.emit(
                self.index(0, 5),
                self.index(self.rowCount() - 1, 9),
                [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole],
            )

    def set_direction_highlighting(self, enabled: bool, *, dark_mode: bool = False) -> None:
        """Toggle presentation-only direction backgrounds / 切换方向背景色。"""

        changed = self._highlight_directions != enabled or self._dark_mode != dark_mode
        self._highlight_directions = enabled
        self._dark_mode = dark_mode
        if changed and self.rowCount():
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, self.columnCount() - 1),
                [Qt.ItemDataRole.BackgroundRole],
            )

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
        if role == FRAME_SORT_ROLE:
            previous = self._frames[index.row() - 1] if index.row() else None
            delta = frame.ts_seconds - previous.ts_seconds if previous is not None else 0.0
            sort_values = {
                0: index.row(),
                1: frame.ts_seconds,
                2: delta,
                3: "" if frame.channel is None else str(frame.channel),
                4: frame.can_id,
                5: annotation.direction if annotation is not None else "other",
                6: frame.dlc,
                7: bytes(frame.data),
                8: annotation.isotp_summary if annotation is not None else "",
                9: annotation.uds_summary if annotation is not None else "",
                10: annotation.summary if annotation is not None else "",
            }
            return sort_values.get(index.column(), "")
        if role == Qt.ItemDataRole.BackgroundRole and self._highlight_directions:
            direction = annotation.direction if annotation is not None else "other"
            colors = (
                {
                    "tester->ecu": "#294B63",
                    "ecu->tester": "#315844",
                    "other": "#454A52",
                }
                if self._dark_mode
                else {
                    "tester->ecu": "#E3F0FB",
                    "ecu->tester": "#E5F4E9",
                    "other": "#EEF0F2",
                }
            )
            return QColor(colors.get(direction, colors["other"]))
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        column = index.column()
        previous = self._frames[index.row() - 1] if index.row() else None
        if column == 0:
            return str(index.row() + 1)
        if column == 1:
            # Display source-aligned absolute epoch seconds.  Δt remains the
            # separate relative interval column.
            return f"{frame.ts_seconds:.6f}"
        if column == 2:
            delta = frame.ts_seconds - previous.ts_seconds if previous is not None else 0.0
            return f"{delta:.6f}"
        if column == 3:
            return "" if frame.channel is None else str(frame.channel)
        if column == 4:
            return f"{frame.can_id:08X}" if frame.is_extended else f"{frame.can_id:03X}"
        if column == 5:
            return direction_label(
                annotation.direction if annotation is not None else "other",
                self._language,
            )
        if column == 6:
            return str(frame.dlc)
        if column == 7:
            return " ".join(f"{byte:02X}" for byte in frame.data)
        if column == 8:
            return annotation.isotp_summary if annotation is not None and annotation.isotp_summary else ""
        if column == 9:
            if annotation is None:
                return ""
            return format_uds_summary(
                annotation.uds_details,
                self._language,
                annotation.uds_summary or "",
            )
        if column == 10:
            return annotation.summary if annotation is not None else "other"
        return None


class FrameTableDelegate(QStyledItemDelegate):
    """Paint byte-level Data cells for rapid protocol inspection."""

    _LIGHT_COLORS = {
        "pci": QColor("#D7EAF8"),
        "sid": QColor("#E9DDF6"),
        "subservice": QColor("#DDF0E2"),
        "did": QColor("#F8E7C8"),
        "payload": QColor("#E8ECF1"),
    }
    _DARK_COLORS = {
        "pci": QColor("#294B63"),
        "sid": QColor("#574276"),
        "subservice": QColor("#315844"),
        "did": QColor("#6A542D"),
        "payload": QColor("#3F4853"),
    }

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._dark_mode = False

    def set_dark_mode(self, enabled: bool) -> None:
        self._dark_mode = enabled

    @staticmethod
    def _byte_roles(frame: RawFrame, annotation: FrameAnnotation | None) -> list[str]:
        """Classify visible bytes using API-provided ISO-TP kind and positions."""

        data_length = len(frame.data)
        roles = ["payload"] * data_length
        if not data_length:
            return roles
        summary = annotation.isotp_summary if annotation is not None else ""
        kind = summary.split(" ", 1)[0].upper() if summary else ""
        pci_length = {"SF": 1, "FF": 2, "CF": 1, "FC": 3}.get(kind, 0)
        for index in range(min(pci_length, data_length)):
            roles[index] = "pci"
        if kind in {"SF", "FF"}:
            payload_start = min(pci_length, data_length)
            if payload_start < data_length:
                roles[payload_start] = "sid"
            if payload_start + 1 < data_length:
                roles[payload_start + 1] = "subservice"
            for index in range(payload_start + 2, min(payload_start + 4, data_length)):
                roles[index] = "did"
        return roles

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index.column() != FRAME_COLUMNS.index("Data"):
            super().paint(painter, option, index)
            return
        frame = index.data(FRAME_OBJECT_ROLE)
        if not isinstance(frame, RawFrame) or not frame.data:
            super().paint(painter, option, index)
            return

        annotation = index.data(ANNOTATION_ROLE)
        colors = self._DARK_COLORS if self._dark_mode else self._LIGHT_COLORS
        painter.save()
        base = (
            option.palette.highlight().color()
            if option.state & QStyle.StateFlag.State_Selected
            else option.palette.alternateBase().color()
            if index.row() % 2
            else option.palette.base().color()
        )
        painter.fillRect(option.rect, base)
        roles = self._byte_roles(frame, annotation)
        padding = 4
        gap = 2
        available = max(1, option.rect.width() - padding * 2 - gap * (len(frame.data) - 1))
        byte_width = max(1, available // len(frame.data))
        show_byte_text = byte_width >= 14
        x = option.rect.left() + padding
        block_height = max(18, option.rect.height() - 8)
        y = option.rect.top() + (option.rect.height() - block_height) // 2
        for value, role_name in zip(frame.data, roles):
            block = QRect(x, y, byte_width, block_height)
            color = QColor(colors[role_name])
            if option.state & QStyle.StateFlag.State_Selected:
                color = color.lighter(115)
            painter.fillRect(block, color)
            painter.setPen(option.palette.text().color())
            if byte_width >= 2:
                painter.drawRect(block.adjusted(0, 0, -1, -1))
            if show_byte_text:
                painter.drawText(block, Qt.AlignmentFlag.AlignCenter, f"{value:02X}")
            x += byte_width + gap
        painter.restore()


class FrameFilterProxyModel(QSortFilterProxyModel):
    """Case-insensitive whole-row filter for the frame table / 帧表过滤器。"""

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)
        self.setSortRole(FRAME_SORT_ROLE)
        self._allowed_directions = {"tester->ecu", "ecu->tester", "functional", "other"}
        self._hide_cf = False

    def set_query(self, query: str) -> None:
        self.setFilterFixedString(query)

    def _refresh_row_filter(self) -> None:
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:  # Qt 6.6 compatibility / 兼容 Qt 6.6
            self.invalidateFilter()

    def set_allowed_directions(self, directions: set[str]) -> None:
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self._allowed_directions = set(directions)
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self._allowed_directions = set(directions)
            self.invalidateFilter()

    def set_hide_cf(self, hidden: bool) -> None:
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self._hide_cf = hidden
            self.endFilterChange(QSortFilterProxyModel.Direction.Rows)
        else:
            self._hide_cf = hidden
            self.invalidateFilter()

    @staticmethod
    def _is_cf(value: object) -> bool:
        return isinstance(value, str) and value.upper().startswith("CF ")

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        source = self.sourceModel()
        if source is None:
            return False
        annotation = source.data(
            source.index(source_row, 0, source_parent), ANNOTATION_ROLE
        )
        direction = getattr(annotation, "direction", "other")
        if direction not in self._allowed_directions:
            return False
        if self._hide_cf:
            isotp = getattr(annotation, "isotp_summary", "")
            if self._is_cf(isotp):
                return False
        return super().filterAcceptsRow(source_row, source_parent)
