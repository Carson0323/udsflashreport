from __future__ import annotations

from .config import (
    config_from_dict,
    config_to_dict,
    default_config,
    load_config,
    save_config,
    validate_config_data,
)
from .models import (
    AddressedFrame,
    AnalysisResult,
    AppConfig,
    ConfigValidationResult,
    ConversationSummary,
    FrameAnnotation,
    TraceBundle,
    TraceQuality,
    TraceWindow,
)
from .addressing import address_frames, group_by_pair_key
from .isotp.events import build_conversations, eventize_frames
from .reader import read_trace


def validate_config(data: dict) -> ConfigValidationResult:
    return validate_config_data(data)


def load_trace(path: str, cfg: AppConfig) -> TraceBundle:
    """Load, address, eventize, and reconstruct an input trace.

    This is the public read-only pipeline.  It preserves the original frame
    chronology, marks physical versus functional addressing, and leaves UDS
    attribution to ``analyze_trace``.
    """

    reader_result = read_trace(path)
    frames = reader_result.frames
    if frames:
        start_ts = frames[0].ts_seconds
        end_ts = frames[-1].ts_seconds
    else:
        start_ts = end_ts = 0.0
    quality = TraceQuality(
        start_ts=start_ts,
        end_ts=end_ts,
        has_capture_gap=None,
        dropped_frame_count=None,
        source_channels=sorted(
            {frame.channel for frame in frames if frame.channel is not None},
            key=lambda channel: (str(type(channel)), str(channel)),
        ),
        filter_state_known=False,
        completeness="unknown",
    )
    window = TraceWindow(start_ts=start_ts, end_ts=end_ts, coverage_ok=True)
    addressed = address_frames(frames, cfg.addressing)
    event_result = eventize_frames(addressed, addressing_mode=cfg.isotp.addressing_mode)
    conversations = build_conversations(
        addressed,
        addressing_mode=cfg.isotp.addressing_mode,
        trace_window=window,
    )

    event_by_ref = {event.frame.frame_ref: event for event in event_result.events}
    addressed_by_ref = {frame.frame_ref: frame for frame in addressed}
    annotations: dict[str, FrameAnnotation] = {}
    for frame in frames:
        addressed_frame = addressed_by_ref.get(frame.frame_ref)
        role = addressed_frame.role if addressed_frame is not None else "other"
        addressing_mode = (
            "functional"
            if role == "functional"
            else "physical"
            if role in {"tester->ecu", "ecu->tester"}
            else "unknown"
        )
        event = event_by_ref.get(frame.frame_ref)
        isotp_summary = _event_summary(event) if event is not None else None
        annotations[frame.frame_ref] = FrameAnnotation(
            frame_ref=frame.frame_ref,
            direction=role,
            isotp_summary=isotp_summary,
            uds_summary=None,
            summary=isotp_summary or role,
            addressing_mode=addressing_mode,
        )

    input_stats = dict(reader_result.input_stats)
    input_stats["trace_quality"] = {
        "start_ts": quality.start_ts,
        "end_ts": quality.end_ts,
        "has_capture_gap": quality.has_capture_gap,
        "dropped_frame_count": quality.dropped_frame_count,
        "source_channels": quality.source_channels,
        "filter_state_known": quality.filter_state_known,
        "completeness": quality.completeness,
    }
    input_stats["unsupported"] = [issue.kind for issue in event_result.issues]
    input_stats["unsupported_counts"] = event_result.input_stats["unsupported_counts"]
    input_stats["unsupported_count"] = len(event_result.issues)
    input_stats["event_count"] = len(event_result.events)

    return TraceBundle(
        path=str(path),
        frames=frames,
        conversations=conversations,
        quality=quality,
        input_stats=input_stats,
        frame_annotations=annotations,
        conversation_summaries=_conversation_summaries(addressed, cfg),
    )


def _event_summary(event: object) -> str:
    kind = getattr(event, "kind")
    if kind == "sf":
        return f"SF len={getattr(event, 'payload_len')}"
    if kind == "ff":
        return f"FF len={getattr(event, 'total_len')}"
    if kind == "cf":
        return f"CF SN={getattr(event, 'sn')}"
    if kind == "fc":
        fs = getattr(event, "fs")
        fs_name = {0: "CTS", 1: "WAIT", 2: "OVFLW"}.get(fs, f"FS={fs}")
        return f"FC {fs_name} BS={getattr(event, 'bs')} STmin={getattr(event, 'stmin_raw'):02X}"
    return str(kind)


def _conversation_summaries(
    addressed: list[AddressedFrame],
    cfg: AppConfig,
) -> list[ConversationSummary]:
    summaries: list[ConversationSummary] = []
    for pair_key, group in group_by_pair_key(addressed).items():
        request = next((frame for frame in group if frame.role == "tester->ecu"), None)
        response = next((frame for frame in group if frame.role == "ecu->tester"), None)
        if request is None and response is None:
            continue
        request_id = request.can_id if request else int(pair_key.split("<->")[0].rsplit(":", 1)[-1], 16)
        response_id = response.can_id if response else int(pair_key.rsplit("<->", 1)[-1], 16)
        name = None
        for manual in cfg.addressing.manual_pairs:
            if (
                manual.channel is None or manual.channel == group[0].channel
            ) and int(manual.request_id, 16) == request_id and int(manual.response_id, 16) == response_id:
                name = manual.name
                break
        summaries.append(
            ConversationSummary(
                pair_key=pair_key,
                channel=group[0].channel,
                name=name,
                request_id=request_id,
                response_id=response_id,
                is_extended_id=(request or response).is_extended,
                frame_count=len(group),
            )
        )
    return sorted(summaries, key=lambda summary: summary.pair_key)


def analyze_trace(bundle: TraceBundle, cfg: AppConfig) -> AnalysisResult:
    from .attribution.engine import analyze_bundle

    return analyze_bundle(bundle, cfg)


def export_report(result: AnalysisResult, md_path: str | None, json_path: str | None) -> dict:
    from .report.json_out import write_json
    from .report.markdown import render_markdown
    from .report.validate import validate_report

    report = dict(result.report_data)
    validation = validate_report(report)
    if not validation.ok:
        raise ValueError("invalid report: " + "; ".join(validation.errors))
    if md_path is not None:
        from pathlib import Path

        output = Path(md_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_markdown(report), encoding="utf-8")
    if json_path is not None:
        write_json(report, json_path)
    return {
        "report": report,
        "validated": True,
        "md_path": md_path,
        "json_path": json_path,
    }


__all__ = [
    "analyze_trace",
    "config_from_dict",
    "config_to_dict",
    "default_config",
    "export_report",
    "load_config",
    "load_trace",
    "save_config",
    "validate_config",
]
