from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QAbstractItemModelTester

from flashreport_core.models import FrameAnnotation, RawFrame
from flashreport_gui.models import (
    FRAME_COLUMNS,
    FRAME_OBJECT_ROLE,
    FrameFilterProxyModel,
    FrameTableDelegate,
    FrameTableModel,
)


def _frame(line_no: int, ts: float, can_id: int = 0x123) -> RawFrame:
    return RawFrame(
        ts_seconds=ts,
        ts_display=f"{ts:.3f}",
        source_ts_metadata={},
        can_id=can_id,
        is_extended=False,
        channel=1,
        is_fd=False,
        dlc=3,
        data=b"\x02\x10\x02",
        source="synthetic",
        line_no=line_no,
    )


def test_frame_table_has_frozen_columns_and_api_annotation_projection(qtbot) -> None:
    frames = [_frame(1, 10.0), _frame(2, 10.125, 0x456)]
    annotations = {
        frames[0].frame_ref: FrameAnnotation(
            frame_ref=frames[0].frame_ref,
            direction="tester->ecu",
            isotp_summary="SF len=2",
            uds_summary="0x10 DiagnosticSessionControl",
            summary="UDS request",
        )
    }
    model = FrameTableModel(frames, annotations, start_ts=10.0)
    tester = QAbstractItemModelTester(
        model,
        QAbstractItemModelTester.FailureReportingMode.Warning,
        model,
    )
    qtbot.addWidget  # keep the test explicitly tied to pytest-qt availability

    assert model.columnCount() == 11
    assert model.headerData(0, Qt.Orientation.Horizontal) == FRAME_COLUMNS[0]
    assert model.data(model.index(0, 1)) == "10.000000"
    assert model.data(model.index(1, 2)) == "0.125000"
    assert model.data(model.index(0, 5)) == "Tester→ECU"
    assert model.data(model.index(0, 8)) == "SF len=2"
    assert model.data(model.index(0, 9)) == "0x10 DiagnosticSessionControl"
    assert model.data(model.index(0, FRAME_COLUMNS.index("Data"))) == "02 10 02"
    assert model.data(model.index(0, 0), FRAME_OBJECT_ROLE).frame_ref == frames[0].frame_ref


def test_frame_filter_searches_all_display_columns() -> None:
    frame = _frame(1, 1.0, 0x7DF)
    model = FrameTableModel([frame])
    proxy = FrameFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_query("7DF")
    assert proxy.rowCount() == 1
    proxy.set_query("does-not-match")
    assert proxy.rowCount() == 0


def test_frame_model_keeps_chronology_and_filters_direction_and_cf() -> None:
    first = _frame(2, 2.0)
    second = _frame(1, 1.0, 0x456)
    third = _frame(3, 3.0, 0x789)
    annotations = {
        first.frame_ref: FrameAnnotation(
            frame_ref=first.frame_ref,
            direction="tester->ecu",
            isotp_summary="CF SN=1",
            uds_summary=None,
            summary="CF SN=1",
        ),
        second.frame_ref: FrameAnnotation(
            frame_ref=second.frame_ref,
            direction="ecu->tester",
            isotp_summary="SF len=2",
            uds_summary=None,
            summary="SF len=2",
        ),
    }
    model = FrameTableModel([first, second, third], annotations, start_ts=1.0)

    assert model.frame_at(0) is second
    assert model.frame_at(1) is first
    assert model.data(model.index(0, 1)) == "1.000000"
    assert model.data(model.index(1, 1)) == "2.000000"

    proxy = FrameFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.set_allowed_directions({"tester->ecu"})
    assert proxy.rowCount() == 1
    proxy.set_allowed_directions({"tester->ecu", "ecu->tester", "other"})
    proxy.set_hide_cf(True)
    assert proxy.rowCount() == 2


def test_frame_delegate_classifies_short_protocol_bytes_without_overflow() -> None:
    frame = _frame(1, 1.0)
    annotation = FrameAnnotation(
        frame_ref=frame.frame_ref,
        direction="tester->ecu",
        isotp_summary="SF len=2",
        uds_summary="0x10 DiagnosticSessionControl",
        summary="UDS request",
    )

    assert FrameTableDelegate._byte_roles(frame, annotation) == [
        "pci",
        "sid",
        "subservice",
    ]
    fd_frame = RawFrame(
        ts_seconds=2.0,
        ts_display="2.000",
        source_ts_metadata={},
        can_id=0x123,
        is_extended=False,
        channel=1,
        is_fd=True,
        dlc=64,
        data=bytes(range(64)),
        source="synthetic",
        line_no=2,
    )
    assert len(FrameTableDelegate._byte_roles(fd_frame, None)) == 64
