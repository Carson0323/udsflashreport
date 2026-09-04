from __future__ import annotations

from flashreport_core.api import default_config, load_trace


def test_load_trace_exposes_m2_conversations_and_annotations() -> None:
    bundle = load_trace("samples/ok_success_full_download.asc", default_config())

    assert bundle.frames
    assert len(bundle.conversations) == 1
    assert bundle.conversation_summaries[0].pair_key == bundle.conversations[0].pair_key
    assert len(bundle.frame_annotations) == len(bundle.frames)
    assert all(annotation.uds_summary is None for annotation in bundle.frame_annotations.values())
    assert any(annotation.isotp_summary == "SF len=2" for annotation in bundle.frame_annotations.values())
    assert bundle.input_stats["event_count"] == 2
