from __future__ import annotations

from types import SimpleNamespace

from flashreport_core.reader import read_asc, read_blf, read_trace


ROOT_SAMPLE = "samples/ok_success_full_download.asc"


def test_read_generated_asc_and_preserve_frame_metadata() -> None:
    result = read_asc(ROOT_SAMPLE)
    assert len(result.frames) == 2
    assert result.input_stats["frame_count"] == len(result.frames)
    assert [frame.ts_seconds for frame in result.frames] == sorted(
        frame.ts_seconds for frame in result.frames
    )
    for frame in result.frames:
        assert frame.source == "asc"
        assert isinstance(frame.data, bytes)
        assert frame.dlc >= 0
        assert frame.frame_ref.startswith("asc:")


def test_asc_fallback_supports_candump_and_explicit_fd_marker(tmp_path) -> None:
    path = tmp_path / "variant.asc"
    path.write_text(
        "(0.100000) can0 18DA10F1##1014020000000000\n"
        "(0.200000) 18DAF110#025002\n",
        encoding="ascii",
    )

    result = read_asc(path, prefer_native=False)

    assert len(result.frames) == 2
    assert result.frames[0].channel == "can0"
    assert result.frames[0].is_fd is True
    assert result.frames[0].data == bytes.fromhex("1014020000000000")
    assert result.frames[1].channel is None
    assert result.input_stats["unknown_channel_count"] == 1
    assert "unknown_channel" in result.input_stats["warnings"]


def test_blf_reader_transmits_record_layer_metadata(monkeypatch, tmp_path) -> None:
    from flashreport_core.reader import blf as blf_module

    path = tmp_path / "capture.blf"
    path.write_bytes(b"not parsed by the fake reader")
    message = SimpleNamespace(
        timestamp=3.5,
        arbitration_id=0x18DA10F1,
        is_extended_id=True,
        channel=2,
        is_fd=True,
        is_remote_frame=False,
        is_error_frame=True,
        dlc=8,
        data=bytes.fromhex("1014020000000000"),
    )
    monkeypatch.setattr(blf_module.can, "BLFReader", lambda _: iter([message]))

    result = read_blf(path)

    assert len(result.frames) == 1
    frame = result.frames[0]
    assert frame.source == "blf"
    assert frame.channel == 2
    assert frame.is_fd is True
    assert frame.is_error_frame is True
    assert frame.is_remote_frame is False


def test_read_trace_dispatches_by_extension() -> None:
    result = read_trace(ROOT_SAMPLE)
    assert result.frames
    assert result.input_stats["source"] == "asc"
