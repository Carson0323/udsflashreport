"""Conversation navigation tree / 会话导航树模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Sequence

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

from flashreport_core.models import ConversationSummary


CONVERSATION_ROLE = int(Qt.ItemDataRole.UserRole) + 1
ConversationRole = CONVERSATION_ROLE


@dataclass
class _TreeNode:
    label: str
    kind: str
    payload: object | None = None
    parent: _TreeNode | None = None
    children: list[_TreeNode] = field(default_factory=list)


class ConversationTreeModel(QAbstractItemModel):
    """Group API-provided conversation summaries by channel."""

    def __init__(
        self,
        summaries: Sequence[ConversationSummary] | None = None,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._root = _TreeNode("", "root")
        self.set_summaries(summaries or ())

    def set_summaries(self, summaries: Sequence[ConversationSummary]) -> None:
        self.beginResetModel()
        self._root = _TreeNode("", "root")
        grouped: dict[object, list[ConversationSummary]] = {}
        for summary in summaries:
            grouped.setdefault(summary.channel, []).append(summary)
        for channel in sorted(grouped, key=lambda value: (value is None, str(value))):
            channel_label = "—" if channel is None else str(channel)
            channel_node = _TreeNode(
                f"Channel {channel_label} / 通道 {channel_label}",
                "channel",
                payload=channel,
                parent=self._root,
            )
            for summary in sorted(grouped[channel], key=lambda item: item.pair_key):
                label = summary.name or summary.pair_key
                channel_node.children.append(
                    _TreeNode(label, "conversation", payload=summary, parent=channel_node)
                )
            self._root.children.append(channel_node)
        self.endResetModel()

    def _node_for_index(self, index: QModelIndex) -> _TreeNode:
        return index.internalPointer() if index.isValid() else self._root

    def index(  # noqa: N802
        self,
        row: int,
        column: int,
        parent: QModelIndex = QModelIndex(),
    ) -> QModelIndex:
        if column != 0 or row < 0:
            return QModelIndex()
        parent_node = self._node_for_index(parent)
        if row >= len(parent_node.children):
            return QModelIndex()
        return self.createIndex(row, column, parent_node.children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:  # noqa: N802
        if not index.isValid():
            return QModelIndex()
        node = self._node_for_index(index)
        parent_node = node.parent
        if parent_node is None or parent_node is self._root:
            return QModelIndex()
        grandparent = parent_node.parent or self._root
        return self.createIndex(grandparent.children.index(parent_node), 0, parent_node)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self._node_for_index(parent).children) if parent.column() <= 0 else 0

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or index.column() != 0:
            return None
        node = self._node_for_index(index)
        if role == Qt.ItemDataRole.DisplayRole:
            return node.label
        if role == CONVERSATION_ROLE:
            return node.payload
        return None

    def node_kind(self, index: QModelIndex) -> str | None:
        if not index.isValid():
            return None
        return self._node_for_index(index).kind
