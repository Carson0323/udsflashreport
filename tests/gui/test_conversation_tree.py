from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt

from flashreport_core.models import ConversationSummary
from flashreport_gui.models import CONVERSATION_ROLE, ConversationTreeModel


def _summary(pair_key: str, channel: int, name: str | None) -> ConversationSummary:
    return ConversationSummary(
        pair_key=pair_key,
        channel=channel,
        name=name,
        request_id=0x18DA10F1,
        response_id=0x18DAF110,
        is_extended_id=True,
        frame_count=2,
    )


def test_conversation_tree_groups_summaries_by_channel() -> None:
    model = ConversationTreeModel(
        [
            _summary("1:18DA10F1<->18DAF110", 1, "ECU-A"),
            _summary("2:18DA20F1<->18DAF120", 2, None),
        ]
    )

    assert model.columnCount() == 1
    assert model.rowCount(QModelIndex()) == 2
    channel_index = model.index(0, 0)
    conversation_index = model.index(0, 0, channel_index)
    assert "Channel 1" in model.data(channel_index, Qt.ItemDataRole.DisplayRole)
    assert model.data(conversation_index) == "ECU-A"
    assert model.data(conversation_index, CONVERSATION_ROLE).pair_key.startswith("1:")
    assert model.parent(conversation_index) == channel_index
