from __future__ import annotations

from flashreport_core.models import (
    AddressedFrame,
    AddressingConfig,
    AnalysisResult,
    AppConfig,
    ConfigValidationResult,
    ConversationSummary,
    Finding,
    FrameAnnotation,
    FrameEvidence,
    IsoTpConversation,
    IsoTpEvent,
    IsoTpPdu,
    ManualPair,
    RawFrame,
    Report,
    ResolvedTimingConfig,
    ResolvedTimingValue,
    RulesConfig,
    TimeoutsConfig,
    TimingProvenance,
    TraceBundle,
    TraceQuality,
    TraceWindow,
    TransportIssue,
    UdsMessage,
    UdsTransaction,
    WindowEvidence,
)


def test_all_m0_models_can_be_instantiated() -> None:
    raw = RawFrame(
        ts_seconds=1.0,
        ts_display="1.000",
        source_ts_metadata={},
        can_id=0x18DA10F1,
        is_extended=True,
        channel=1,
        is_fd=False,
        dlc=8,
        data=b"\x02\x10\x02",
        source="asc",
        line_no=1,
    )
    addressed = AddressedFrame(role="tester->ecu", pair_key="1:18DA10F1<->18DAF110", **raw.__dict__)
    event = IsoTpEvent(
        kind="sf",
        ts=1.0,
        frame=addressed,
        pci_raw=0x02,
        payload_len=2,
        total_len=None,
        sn=None,
        fs=None,
        bs=None,
        stmin_raw=None,
    )
    window = TraceWindow(start_ts=1.0, end_ts=2.0, coverage_ok=True)
    pdu = IsoTpPdu(
        pair_key="1:18DA10F1<->18DAF110",
        direction="tester->ecu",
        pci="single",
        payload=b"\x10\x02",
        ts_start=1.0,
        ts_end=1.0,
        frames=[addressed],
    )
    conversation = IsoTpConversation(
        pair_key="1:18DA10F1<->18DAF110",
        tester_to_ecu_events=[event],
        ecu_to_tester_events=[],
        pdus=[pdu],
        trace_window=window,
    )
    quality = TraceQuality(
        start_ts=1.0,
        end_ts=2.0,
        has_capture_gap=None,
        dropped_frame_count=None,
        source_channels=[1],
        filter_state_known=False,
        completeness="assumed",
    )
    frame_evidence = FrameEvidence(
        frame_ref=addressed.frame_ref,
        ts=1.0,
        line_no=1,
        can_id=addressed.can_id,
        role=addressed.role,
        data=addressed.data,
        summary="SF",
    )
    window_evidence = WindowEvidence(
        ts_start=1.0,
        ts_end=2.0,
        expected_role="ecu->tester",
        expected_kind="FC",
        expected_can_id=0x18DAF110,
        matched_frame_count=0,
        trace_coverage_ok=True,
        summary="No FC",
    )
    issue = TransportIssue(
        kind="missing_fc_after_ff",
        ts=2.0,
        severity="error",
        observed="none",
        expected="FC",
        evidence=[frame_evidence, window_evidence],
    )
    message = UdsMessage(
        sid=0x10,
        service_name="DiagnosticSessionControl",
        subfunction=0x02,
        did=None,
        block_seq=None,
        max_block_length=None,
        is_positive=True,
        nrc=None,
        nrc_text=None,
        raw=b"\x50\x02",
    )
    transaction = UdsTransaction(
        request=message,
        pending_events=[],
        final_response=message,
        pdu_req=pdu,
        pdu_resp=None,
    )
    finding = Finding(
        finding_id="ISO-TP-001",
        layer="ISO-TP",
        category="missing_fc_after_ff",
        deviation_ts=2.0,
        detected_ts=2.0,
        observed="none",
        expected="FC",
        suspected_side="ecu",
        confidence="medium",
        session="programming",
        service=None,
        detail={"timeout_ms": 1000, "timing_source": "default_assumption"},
        evidence=[frame_evidence, window_evidence],
    )
    annotation = FrameAnnotation(
        frame_ref=addressed.frame_ref,
        direction="tester->ecu",
        isotp_summary="SF",
        uds_summary=None,
        summary="DiagnosticSessionControl",
    )
    summary = ConversationSummary(
        pair_key=conversation.pair_key,
        channel=1,
        name="ECU1",
        request_id=0x18DA10F1,
        response_id=0x18DAF110,
        is_extended_id=True,
        frame_count=1,
    )
    bundle = TraceBundle(
        path="sample.asc",
        frames=[raw],
        conversations=[conversation],
        quality=quality,
        input_stats={"frame_count": 1},
        frame_annotations={raw.frame_ref: annotation},
        conversation_summaries=[summary],
    )
    result = AnalysisResult(
        bundle=bundle,
        findings=[finding],
        first_deviation=finding,
        report_data={},
        frame_annotations=bundle.frame_annotations,
        conversation_summaries=bundle.conversation_summaries,
    )
    report = Report(
        schema_version="1.2",
        tool="flashreport",
        version="0.1.0.dev0",
        source_file="sample.asc",
        generated_at="1970-01-01T00:00:00Z",
        input_stats={},
        findings=[finding],
        first_deviation=finding,
        summary={},
    )
    manual_pair = ManualPair(
        name="ECU1",
        request_id="18DA10F1",
        response_id="18DAF110",
        channel=1,
    )
    config = AppConfig(
        addressing=AddressingConfig(manual_pairs=(manual_pair,)),
        timeouts=TimeoutsConfig(),
        rules=RulesConfig(),
    )
    timing_provenance = TimingProvenance()
    timing = ResolvedTimingConfig(
        isotp_fc=ResolvedTimingValue(value_ms=1000, source=timing_provenance.isotp_fc),
        isotp_cf=ResolvedTimingValue(value_ms=1000, source=timing_provenance.isotp_cf),
        uds_p2=ResolvedTimingValue(value_ms=50, source=timing_provenance.uds_p2),
        uds_p2_star=ResolvedTimingValue(value_ms=5000, source=timing_provenance.uds_p2_star),
    )
    validation = ConfigValidationResult(ok=True, errors=[])

    assert raw.frame_ref == "asc:1"
    assert transaction.final_response is message
    assert result.first_deviation is finding
    assert report.first_deviation is finding
    assert config.addressing.manual_pairs == (manual_pair,)
    assert timing.uds_p2.value_ms == 50
    assert validation.ok
    assert issue.evidence[0].type == "frame"

