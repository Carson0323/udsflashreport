from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ChannelId = int | str


# ---------- frames ----------
@dataclass(kw_only=True)
class RawFrame:
    ts_seconds: float
    ts_display: str
    source_ts_metadata: dict
    can_id: int
    is_extended: bool
    channel: int | str | None
    is_fd: bool
    dlc: int
    data: bytes
    source: str
    line_no: int
    is_remote_frame: bool = False
    is_error_frame: bool = False

    @property
    def frame_ref(self) -> str:
        return f"{self.source}:{self.line_no}"


@dataclass(kw_only=True)
class AddressedFrame(RawFrame):
    role: str
    pair_key: str | None


# ---------- iso-tp ----------
@dataclass(kw_only=True)
class IsoTpEvent:
    kind: str
    ts: float
    frame: AddressedFrame
    pci_raw: int
    payload_len: int | None
    total_len: int | None
    sn: int | None
    fs: int | None
    bs: int | None
    stmin_raw: int | None


@dataclass(kw_only=True)
class IsoTpConversation:
    pair_key: str
    tester_to_ecu_events: list[IsoTpEvent]
    ecu_to_tester_events: list[IsoTpEvent]
    pdus: list[IsoTpPdu]
    trace_window: TraceWindow


@dataclass(kw_only=True)
class IsoTpPdu:
    pair_key: str
    direction: str
    pci: str
    payload: bytes | None
    ts_start: float
    ts_end: float
    frames: list[AddressedFrame]
    incomplete: bool = False
    incomplete_reason: str | None = None
    issues: list[TransportIssue] = field(default_factory=list)


# ---------- trace quality ----------
@dataclass(kw_only=True)
class TraceWindow:
    start_ts: float
    end_ts: float
    coverage_ok: bool


@dataclass(kw_only=True)
class TraceQuality:
    start_ts: float
    end_ts: float
    has_capture_gap: bool | None
    dropped_frame_count: int | None
    source_channels: list[ChannelId]
    filter_state_known: bool
    completeness: Literal["verified", "assumed", "unknown", "known_incomplete"]


# ---------- evidence ----------
@dataclass(kw_only=True)
class FrameEvidence:
    type: Literal["frame"] = "frame"
    frame_ref: str
    ts: float
    line_no: int
    can_id: int
    role: str
    data: bytes
    summary: str


@dataclass(kw_only=True)
class WindowEvidence:
    type: Literal["absence_window"] = "absence_window"
    ts_start: float
    ts_end: float
    expected_role: str
    expected_kind: str
    expected_can_id: int | None
    matched_frame_count: int
    trace_coverage_ok: bool
    summary: str


Evidence = FrameEvidence | WindowEvidence


# ---------- transport issue ----------
@dataclass(kw_only=True)
class TransportIssue:
    kind: str
    ts: float
    severity: Literal["error", "warning"]
    observed: str
    expected: str
    evidence: list[Evidence]


# ---------- uds / session ----------
@dataclass(kw_only=True)
class UdsMessage:
    sid: int | None
    service_name: str | None
    subfunction: int | None
    did: int | None
    block_seq: int | None
    max_block_length: int | None
    is_positive: bool | None
    nrc: int | None
    nrc_text: str | None
    pending: bool = False
    raw: bytes


@dataclass(kw_only=True)
class UdsTransaction:
    request: UdsMessage
    pending_events: list[UdsMessage]
    final_response: UdsMessage | None
    pdu_req: IsoTpPdu | None
    pdu_resp: IsoTpPdu | None
    ambiguous: bool = False


# ---------- finding ----------
TimingSource = Literal[
    "observed_server",
    "user_configured",
    "normative_confirmed",
    "default_assumption",
]


@dataclass(frozen=True, kw_only=True)
class TimingProvenance:
    isotp_fc: TimingSource = "default_assumption"
    isotp_cf: TimingSource = "default_assumption"
    uds_p2: TimingSource = "default_assumption"
    uds_p2_star: TimingSource = "default_assumption"


@dataclass(frozen=True, kw_only=True)
class ResolvedTimingValue:
    value_ms: int
    source: TimingSource


@dataclass(frozen=True, kw_only=True)
class ResolvedTimingConfig:
    isotp_fc: ResolvedTimingValue
    isotp_cf: ResolvedTimingValue
    uds_p2: ResolvedTimingValue
    uds_p2_star: ResolvedTimingValue


@dataclass(kw_only=True)
class Finding:
    finding_id: str
    layer: str
    category: str
    deviation_ts: float
    detected_ts: float
    observed: str
    expected: str
    suspected_side: str
    confidence: str
    session: str | None
    service: str | None
    detail: dict
    evidence: list[Evidence]
    superseded_by: str | None = None
    needs_normative_confirmation: bool = False


# ---------- report ----------
@dataclass(kw_only=True)
class Report:
    schema_version: str
    tool: str
    version: str
    source_file: str
    generated_at: str
    input_stats: dict
    findings: list[Finding]
    first_deviation: Finding | None
    summary: dict


# ---------- config ----------
@dataclass(frozen=True, kw_only=True)
class ManualPair:
    name: str
    request_id: str
    response_id: str
    channel: int | str | None = None
    is_extended_id: bool = True


@dataclass(frozen=True, kw_only=True)
class AddressingConfig:
    auto_detect: bool = True
    tester_sa: str = "F1"
    enable_11bit_heuristic: bool = True
    enable_29bit_normal_fixed: bool = True
    manual_pairs: tuple[ManualPair, ...] = ()


@dataclass(frozen=True, kw_only=True)
class IsoTpConfig:
    addressing_mode: str = "auto"


@dataclass(frozen=True, kw_only=True)
class TimeoutsConfig:
    isotp_fc_ms: int = 1000
    isotp_cf_ms: int = 1000
    uds_p2_ms: int = 50
    uds_p2_star_ms: int = 5000


@dataclass(frozen=True, kw_only=True)
class RulesConfig:
    iso_tp_001: bool = True
    iso_tp_002: bool = True
    iso_tp_003: bool = True
    iso_tp_004: bool = True
    iso_tp_005: bool = True
    uds_001: bool = True
    uds_002: bool = True
    flash_001: bool = True


@dataclass(frozen=True, kw_only=True)
class AppConfig:
    schema_version: str = "1.2"
    addressing: AddressingConfig = AddressingConfig()
    isotp: IsoTpConfig = IsoTpConfig()
    timeouts: TimeoutsConfig = TimeoutsConfig()
    rules: RulesConfig = RulesConfig()


@dataclass(kw_only=True)
class ConfigValidationResult:
    ok: bool
    errors: list[str]


RULE_CONFIG_KEYS = {
    "iso_tp_001": "ISO-TP-001",
    "iso_tp_002": "ISO-TP-002",
    "iso_tp_003": "ISO-TP-003",
    "iso_tp_004": "ISO-TP-004",
    "iso_tp_005": "ISO-TP-005",
    "uds_001": "UDS-001",
    "uds_002": "UDS-002",
    "flash_001": "FLASH-001",
}


# ---------- GUI projection ----------
@dataclass(frozen=True, kw_only=True)
class FrameAnnotation:
    frame_ref: str
    direction: str
    isotp_summary: str | None
    uds_summary: str | None
    summary: str
    addressing_mode: str = "unknown"
    uds_details: dict = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class ConversationSummary:
    pair_key: str
    channel: int | str | None
    name: str | None
    request_id: int
    response_id: int
    is_extended_id: bool
    frame_count: int


# ---------- api objects ----------
@dataclass(kw_only=True)
class TraceBundle:
    path: str
    frames: list[RawFrame]
    conversations: list[IsoTpConversation]
    quality: TraceQuality
    input_stats: dict
    frame_annotations: dict[str, FrameAnnotation]
    conversation_summaries: list[ConversationSummary]


@dataclass(kw_only=True)
class AnalysisResult:
    bundle: TraceBundle
    findings: list[Finding]
    first_deviation: Finding | None
    report_data: dict
    frame_annotations: dict[str, FrameAnnotation]
    conversation_summaries: list[ConversationSummary]
    workflow_steps: list[dict] = field(default_factory=list)
