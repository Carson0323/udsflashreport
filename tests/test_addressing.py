from __future__ import annotations

from copy import deepcopy

from flashreport_core.addressing import address_frames, make_pair_key
from flashreport_core.api import default_config, validate_config
from flashreport_core.models import AddressingConfig, ManualPair, RawFrame


def raw(can_id: int, *, channel: int | str | None = 1, is_extended: bool = True) -> RawFrame:
    return RawFrame(
        ts_seconds=1.0,
        ts_display="1.000000",
        source_ts_metadata={},
        can_id=can_id,
        is_extended=is_extended,
        channel=channel,
        is_fd=False,
        dlc=8,
        data=bytes(8),
        source="asc",
        line_no=1,
    )


def assert_29bit_pair(tester_sa: int) -> None:
    ecu_sa = 0x10
    request_id = 0x18DA0000 | (ecu_sa << 8) | tester_sa
    response_id = 0x18DA0000 | (tester_sa << 8) | ecu_sa
    addressed = address_frames(
        [raw(request_id), raw(response_id)],
        AddressingConfig(tester_sa=f"{tester_sa:02X}"),
    )
    assert [frame.role for frame in addressed] == ["tester->ecu", "ecu->tester"]
    expected_key = make_pair_key(1, request_id, response_id)
    assert {frame.pair_key for frame in addressed} == {expected_key}


def test_mask_tester_sa_f1() -> None:
    assert_29bit_pair(0xF1)


def test_mask_tester_sa_e0() -> None:
    assert_29bit_pair(0xE0)


def test_mask_tester_sa_01() -> None:
    assert_29bit_pair(0x01)


def test_mask_regression_v09() -> None:
    configured = AddressingConfig(tester_sa="E0")
    addressed = address_frames([raw(0x18DA10F1)], configured)
    assert addressed[0].role == "other"
    assert addressed[0].pair_key is None


def test_multi_channel_same_ids_isolated() -> None:
    frames = [
        raw(0x7E0, channel=1, is_extended=False),
        raw(0x7E8, channel=1, is_extended=False),
        raw(0x7E0, channel=2, is_extended=False),
        raw(0x7E8, channel=2, is_extended=False),
    ]
    addressed = address_frames(frames, AddressingConfig())
    assert [frame.role for frame in addressed] == [
        "tester->ecu",
        "ecu->tester",
        "tester->ecu",
        "ecu->tester",
    ]
    assert len({frame.pair_key for frame in addressed}) == 2
    assert {frame.pair_key for frame in addressed} == {
        "1:000007E0<->000007E8",
        "2:000007E0<->000007E8",
    }


def test_11bit_pair_and_functional_frame() -> None:
    addressed = address_frames(
        [
            raw(0x7E0, is_extended=False),
            raw(0x7E8, is_extended=False),
            raw(0x18DB33F1, is_extended=True),
        ],
        AddressingConfig(),
    )
    assert [frame.role for frame in addressed] == [
        "tester->ecu",
        "ecu->tester",
        "functional",
    ]
    assert addressed[2].pair_key is None


def test_manual_pair_has_priority_and_preserves_can_id_semantics() -> None:
    config = AddressingConfig(
        manual_pairs=(
            ManualPair(
                name="manual",
                request_id="7E0",
                response_id="7E8",
                channel=3,
                is_extended_id=False,
            ),
        )
    )
    addressed = address_frames(
        [raw(0x7E0, channel=3, is_extended=False), raw(0x7E8, channel=3, is_extended=False)],
        config,
    )
    assert {frame.pair_key for frame in addressed} == {"3:000007E0<->000007E8"}


def test_old_extended_field_is_rejected() -> None:
    data = deepcopy(__import__("flashreport_core.config", fromlist=["config_to_dict"]).config_to_dict(default_config()))
    data["addressing"]["manual_pairs"] = [
        {
            "name": "legacy",
            "request_id": "7E0",
            "response_id": "7E8",
            "channel": 1,
            "extended": False,
        }
    ]
    result = validate_config(data)
    assert not result.ok
    assert any("unknown field extended" in error for error in result.errors)
