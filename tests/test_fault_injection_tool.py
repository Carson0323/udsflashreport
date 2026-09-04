from tools.inject_private_corpus import TraceRecord, inject


def _record(index: int, can_id: int, data: bytes) -> TraceRecord:
    return TraceRecord(
        timestamp=index / 1000,
        can_id=can_id,
        data=data,
        channel=1,
        is_extended=True,
        is_fd=False,
    )


def _trace() -> list[TraceRecord]:
    return [
        _record(0, 0x700, bytes([0x03, 0x34, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF])),
        _record(1, 0x708, bytes([0x03, 0x74, 0x20, 0x00, 0xFF, 0xFF, 0xFF, 0xFF])),
        _record(2, 0x700, bytes([0x10, 0x10, 0x36, 0x01, 0x02, 0x03, 0x04, 0x05])),
        _record(3, 0x708, bytes([0x30, 0x08, 0x05, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])),
        _record(4, 0x700, bytes([0x21, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C])),
        _record(5, 0x700, bytes([0x22, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13])),
    ]


def test_fault_injection_variants_are_deterministic_and_non_mutating() -> None:
    original = _trace()
    cut = inject(original, "cut_after_stage_timeout")
    missing_fc = inject(original, "missing_flow_control_timeout")
    negative = inject(original, "ecu_negative_response")
    sequence = inject(original, "cf_sequence_violation")

    assert all(item.status == "INJECTED" for item in (cut, missing_fc, negative, sequence))
    assert len(cut.records) == 3
    assert cut.records[-1].data[0] == 0x10
    assert len(missing_fc.records) == len(original) - 1
    assert missing_fc.records[3].data[0] == 0x21
    assert any(record.data[:4] == bytes([0x03, 0x7F, 0x34, 0x72]) for record in negative.records)
    assert sequence.records[4].data[0] == 0x22
    assert sequence.records[5].data[0] == 0x21
    assert original[4].data[0] == 0x21
