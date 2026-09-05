"""User-visible failures found during the 1.0.1 engineering review."""

import pytest

from flashreport_core.api import analyze_trace, default_config, export_report, load_trace
from flashreport_core.cli import main
from flashreport_core.config import config_to_dict, validate_config_data
from flashreport_core.reader.asc import read_asc
from flashreport_core.uds.decoder import decode_uds
from flashreport_core.uds.pending import TimedUdsMessage
from flashreport_core.uds.transaction_matcher import match_transactions


def timed(ts, raw):
    return TimedUdsMessage(ts=ts, message=decode_uds(bytes.fromhex(raw)))


def test_download_unequal_field_widths_agree_across_projections(tmp_path):
    trace = tmp_path / "download.asc"
    # ALFID 0x12: two address bytes, one size byte.
    trace.write_text("0.0 1 7E0 Rx d 7 06 34 00 12 AB CD 20\n", encoding="ascii")
    cfg = default_config()
    result = analyze_trace(load_trace(str(trace), cfg), cfg)
    assert result.workflow_steps[0]["fields"]["start_address"] == 0xABCD
    assert result.workflow_steps[0]["fields"]["transfer_length"] == 0x20
    annotation = next(iter(result.frame_annotations.values()))
    assert annotation.uds_details["start_address"] == 0xABCD
    assert annotation.uds_details["transfer_length"] == 0x20


@pytest.mark.parametrize("response", ["62F191", "7F2278", "7F2231", "5003", "50"])
def test_unrelated_or_truncated_response_does_not_close_request(response):
    result = match_transactions([timed(0, "1002")], [timed(.1, response)])
    assert result[0].final_response is None
    assert not result[0].pending_events
    assert result.ambiguous


def test_interleaved_response_matches_service_instead_of_latest_request():
    result = match_transactions(
        [timed(0, "1002"), timed(.1, "22F190")],
        [timed(.2, "7F1078"), timed(.3, "5002"), timed(.4, "62F19041")],
    )
    assert result[0].final_response.sid == 0x50
    assert len(result[0].pending_events) == 1
    assert result[1].final_response.sid == 0x62
    assert result.ambiguous


@pytest.mark.parametrize("request_hex,response", [("22F190", "62F191"), ("3601AA", "7602"), ("31011234", "71015678")])
def test_echoed_identifiers_must_match(request_hex, response):
    result = match_transactions([timed(0, request_hex)], [timed(.1, response)])
    assert result[0].final_response is None
    assert result.ambiguous


def test_candump_fd_flags_remote_and_empty_data_are_distinct(tmp_path):
    trace = tmp_path / "candump.asc"
    trace.write_text("(0.1) can0 123##1AABB\n(0.2) can0 123#R8\n(0.3) can0 123#\n", encoding="ascii")
    frames = read_asc(trace, prefer_native=False).frames
    assert len(frames) == 3
    assert frames[0].is_fd and frames[0].data == bytes.fromhex("AABB")
    assert frames[1].is_remote_frame and frames[1].dlc == 8
    assert not frames[2].is_remote_frame and frames[2].data == b""


def test_skipped_record_marks_trace_incomplete(tmp_path):
    trace = tmp_path / "damaged.asc"
    trace.write_text("0.0 1 7E0 Rx d 3 02 10 02\n0.1 1 7E8 Rx d 3 02 50\n", encoding="ascii")
    bundle = load_trace(str(trace), default_config())
    assert bundle.input_stats["skipped_object_count"] == 1
    assert bundle.quality.completeness == "known_incomplete"
    assert not bundle.conversations[0].trace_window.coverage_ok


def test_empty_input_is_an_error_not_no_findings(tmp_path, capsys):
    trace = tmp_path / "empty.asc"
    trace.write_text("not a CAN trace\n", encoding="ascii")
    assert main(["analyze", str(trace)]) == 2
    assert "NO FINDINGS" not in capsys.readouterr().out


def test_malformed_yaml_returns_configuration_exit_code(tmp_path, capsys):
    (tmp_path / "findings.yaml").write_text("findings: [\n", encoding="ascii")
    assert main(["analyze", "samples/success_full_download.asc", "--spec", str(tmp_path)]) == 3
    assert "invalid spec" in capsys.readouterr().out


def test_incomplete_registry_returns_configuration_exit_code(tmp_path):
    (tmp_path / "findings.yaml").write_text("findings: []\n", encoding="ascii")
    assert main(["analyze", "samples/success_full_download.asc", "--spec", str(tmp_path)]) == 3


@pytest.mark.parametrize("field,value", [("tester_sa", "GG"), ("tester_sa", "123"), ("tester_sa", "")])
def test_invalid_tester_address_is_rejected(field, value):
    data = config_to_dict(default_config())
    data["addressing"][field] = value
    assert not validate_config_data(data).ok


def test_non_scalar_addressing_mode_is_validation_error():
    data = config_to_dict(default_config())
    data["isotp"]["addressing_mode"] = []
    assert not validate_config_data(data).ok


@pytest.mark.parametrize("can_id,extended,channel", [("XYZ", False, 1), ("800", False, 1), ("20000000", True, 1), ("700", False, True)])
def test_invalid_manual_pair_is_rejected(can_id, extended, channel):
    data = config_to_dict(default_config())
    data["addressing"]["manual_pairs"] = [{
        "name": "ECU", "request_id": can_id, "response_id": "708",
        "is_extended_id": extended, "channel": channel,
    }]
    assert not validate_config_data(data).ok


def test_reader_reports_original_timestamp_order_and_rejects_nonfinite(tmp_path):
    trace = tmp_path / "timestamps.asc"
    trace.write_text("0.2 1 7E0 Rx d 3 02 10 02\n0.1 1 7E8 Rx d 3 02 50 02\nnan 1 7E0 Rx d 3 02 10 02\n", encoding="ascii")
    result = read_asc(trace, prefer_native=False)
    assert not result.input_stats["time_monotonic"]
    assert "timestamps_reordered" in result.input_stats["warnings"]
    assert result.input_stats["skipped_object_count"] == 1
    assert [frame.ts_seconds for frame in result.frames] == [.1, .2]


@pytest.mark.parametrize("flag", ["auto_detect", "enable_29bit_normal_fixed"])
def test_dynamic_pairing_respects_disabled_detection(flag):
    from dataclasses import replace
    cfg = default_config()
    cfg = replace(cfg, addressing=replace(cfg.addressing, **{flag: False}))
    assert load_trace("samples/success_full_download.asc", cfg).conversations == []


def test_export_cannot_overwrite_input_or_use_same_output(tmp_path):
    trace = tmp_path / "source.asc"
    original = "0.0 1 7E0 Rx d 3 02 10 02\n"
    trace.write_text(original, encoding="ascii")
    cfg = default_config()
    result = analyze_trace(load_trace(str(trace), cfg), cfg)
    with pytest.raises(ValueError):
        export_report(result, str(trace), None)
    assert trace.read_text(encoding="ascii") == original
    target = tmp_path / "same.json"
    with pytest.raises(ValueError):
        export_report(result, str(target), str(target))
    assert not target.exists()
