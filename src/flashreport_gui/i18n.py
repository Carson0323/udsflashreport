from __future__ import annotations

"""Small runtime language table for GUI chrome / GUI 界面语言表。"""

import re

LANGUAGE_CODES = ("zh", "en")
LANGUAGE_LABELS = {"zh": "中文", "en": "English"}

_TEXT = {
    "zh": {
        "app_title": "FlashReport / UDS 刷写 Trace 分析",
        "brand": "FlashReport / Trace 分析",
        "author_info": "作者：{author} · 邮箱：{email} · 版本：v{version}",
        "open": "打开",
        "analyze": "分析",
        "export": "导出",
        "settings": "设置",
        "language": "语言",
        "switch_light": "浅色模式",
        "switch_dark": "深色模式",
        "conversations": "会话",
        "can_frames": "CAN 帧",
        "findings": "发现",
        "no_findings": "未发现协议偏差",
        "finding_count": "发现数量：{count}",
        "finding_focus": "发现数量：{count} · 选择一条以定位证据",
        "filter": "筛选",
        "search_placeholder": "搜索 CAN ID / Data / UDS",
        "other": "其他",
        "show_cf": "显示 CF",
        "color_direction": "方向着色",
        "functional": "功能寻址",
        "data_legend": "PCI · SID · 子服务 · DID",
        "empty_trace": "请打开 ASC/BLF Trace 开始分析",
        "loading": "正在加载 Trace…",
        "analyzing": "正在分析…",
        "trace_loaded": "Trace 已加载",
        "analysis_completed": "分析完成",
        "exporting": "正在导出报告…",
        "exported": "报告已导出",
        "open_dialog": "打开 Trace",
        "export_dialog": "导出报告",
        "settings_dialog": "设置",
        "tester_sa": "Tester SA",
        "auto_detect": "自动检测",
        "addressing_label": "寻址",
        "enable_11bit": "启用 11 位启发式",
        "enable_29bit": "启用 29 位标准地址",
        "isotp_mode": "ISO-TP 模式",
        "fc_timeout": "ISO-TP FC 超时（ms）",
        "cf_timeout": "ISO-TP CF 超时（ms）",
        "p2_timeout": "UDS P2 超时（ms）",
        "p2_star_timeout": "UDS P2* 超时（ms）",
        "load_json": "加载 JSON",
        "save_json": "保存 JSON",
        "save": "保存",
        "cancel": "取消",
        "load_config_dialog": "加载配置",
        "save_config_dialog": "保存配置",
        "save_failed": "保存失败",
        "load_error": "无法加载 Trace：{message}",
        "analysis_error": "分析失败：{message}",
        "export_error": "导出失败：{message}",
        "invalid_load": "加载器返回结果无效",
        "invalid_analysis": "分析结果无效",
        "error": "错误",
        "frames_status": "帧：{count}",
        "findings_status": "发现：{count}",
        "channel_status": "CH：{channels}",
        "select_frame": "请选择一帧",
        "no_isotp": "暂无 ISO-TP 详情",
        "no_uds": "暂无 UDS 详情",
        "no_session": "暂无会话详情",
        "select_evidence": "请选择证据",
        "frame_details": "帧详情",
        "session_details": "会话",
        "evidence": "证据",
        "workflow": "刷写流程",
        "expand_transfer": "展开 TransferData 分段",
        "collapse_transfer": "合并 TransferData 统计",
        "workflow_empty": "未识别到 UDS 请求或功能寻址步骤",
        "unknown_service": "未知服务",
        "manual_review": "需人工复核",
        "manual_reason": "人工复核原因：{reason}",
        "orphan_reason": "存在未关联到未完成请求的 ECU 负响应，已按同 SID 的最近请求定位，需确认真实时序。",
        "no_rule_reason": "没有规则产生 Finding；请结合输入质量、未支持项和原始 Trace 复核。",
        "unsupported_reason": "存在 {count} 个未支持/无法解析的记录，不能据此自动下结论。",
        "ambiguous_reason": "存在 {count} 个请求/响应匹配歧义，责任侧或时序不能唯一确定。",
        "coverage_reason": "输入完整性：{value}；缺失窗口的置信度受到限制。",
        "finding_title": "{id} / {layer}",
        "confidence": "置信度：{value}",
        "side": "责任侧：{value}",
        "deviation": "偏差时刻：{value:.6f}s",
        "detected": "检测时刻：{value:.6f}s",
        "observed": "观测：{value}",
        "expected": "期望：{value}",
        "jump": "定位",
        "show": "查看",
        "frame_line": "行 {line} · t={time:.6f}s · CAN ID={can_id}",
        "interval": "区间 {start:.6f}s–{end:.6f}s · 命中帧 {count}",
        "finding_context": "Finding：{id}",
        "frame": "帧：{value}",
        "time": "时间：{value}",
        "channel": "CH：{value}",
        "can_id": "CAN ID：{value}",
        "dlc": "DLC：{value}",
        "data": "Data：{value}",
        "direction": "方向：{value}",
        "isotp": "ISO-TP：{value}",
        "uds": "UDS：{value}",
        "addressing": "寻址：{value}",
        "service": "服务：{value}",
        "did": "DID：{value}",
        "did_bytes": "DID 字节：{value}",
        "did_ascii": "DID ASCII：{value}",
        "subfunction": "子功能：{value}",
        "subfunction_detail": "子功能：{value}（{description}）",
        "nrc": "NRC：{value}",
        "bsc": "BSC：{value}",
        "session": "会话：{value}",
        "read_data": "读取数据：{value}",
        "read_ascii": "读取 ASCII：{value}",
        "write_data": "写入数据：{value}",
        "write_ascii": "写入 ASCII：{value}",
        "ascii": "ASCII：{value}",
        "routine_id": "RoutineID：{value}",
        "parameters": "参数：{value}",
        "start_address": "起始地址：{value}",
        "transfer_length": "长度：{value}",
        "transfer_bytes": "传输字节：{value}",
        "transfer_segments": "TransferData 分段：{count} · 总字节：{bytes} · BSC：{start}–{end}",
        "raw_uds": "原始 UDS：{value}",
        "location_frame": "帧：{value}",
        "anchor_frame": "定位锚点帧：{value}",
        "location_interval": "区间：{value:.6f}s–{value_end:.6f}s",
        "expected_role": "期望方向：{value}",
        "expected_kind": "期望类型：{value}",
        "matched_frames": "命中帧数：{value}",
        "coverage": "覆盖完整：{value}",
        "data_label": "Data：{value}",
        "no_response": "未收到最终响应",
        "negative": "ECU 返回负响应",
        "positive": "收到正响应",
        "functional_step": "功能寻址请求",
        "physical": "物理寻址",
        "functional_addressing": "功能寻址",
        "status": "状态：{value}",
        "workflow_step": "步骤 {index} · t={time:.6f}s · {addressing} · {status}",
    },
    "en": {
        "app_title": "FlashReport / UDS Flash Trace Analysis",
        "brand": "FlashReport / Trace Analysis",
        "author_info": "Author: {author} · Email: {email} · Version: v{version}",
        "open": "Open",
        "analyze": "Analyze",
        "export": "Export",
        "settings": "Settings",
        "language": "Language",
        "switch_light": "Light mode",
        "switch_dark": "Dark mode",
        "conversations": "Conversations",
        "can_frames": "CAN Frames",
        "findings": "Findings",
        "no_findings": "No protocol deviations found",
        "finding_count": "Findings: {count}",
        "finding_focus": "Findings: {count} · Select one to focus evidence",
        "filter": "Filter",
        "search_placeholder": "Search CAN ID / Data / UDS",
        "other": "Other",
        "show_cf": "Show CF",
        "color_direction": "Color direction",
        "functional": "Functional",
        "data_legend": "PCI · SID · Subservice · DID",
        "empty_trace": "Open an ASC/BLF trace to begin analysis",
        "loading": "Loading trace…",
        "analyzing": "Analyzing…",
        "trace_loaded": "Trace loaded",
        "analysis_completed": "Analysis completed",
        "exporting": "Exporting report…",
        "exported": "Report exported",
        "open_dialog": "Open trace",
        "export_dialog": "Export report",
        "settings_dialog": "Settings",
        "tester_sa": "Tester SA",
        "auto_detect": "Auto detect",
        "addressing_label": "Addressing",
        "enable_11bit": "Enable 11-bit heuristic",
        "enable_29bit": "Enable 29-bit normal fixed",
        "isotp_mode": "ISO-TP mode",
        "fc_timeout": "ISO-TP FC timeout (ms)",
        "cf_timeout": "ISO-TP CF timeout (ms)",
        "p2_timeout": "UDS P2 timeout (ms)",
        "p2_star_timeout": "UDS P2* timeout (ms)",
        "load_json": "Load JSON",
        "save_json": "Save JSON",
        "save": "Save",
        "cancel": "Cancel",
        "load_config_dialog": "Load configuration",
        "save_config_dialog": "Save configuration",
        "save_failed": "Save failed",
        "load_error": "Unable to load trace: {message}",
        "analysis_error": "Analysis failed: {message}",
        "export_error": "Export failed: {message}",
        "invalid_load": "Invalid loader result",
        "invalid_analysis": "Invalid analysis result",
        "error": "Error",
        "frames_status": "Frames: {count}",
        "findings_status": "Findings: {count}",
        "channel_status": "CH: {channels}",
        "select_frame": "Select a frame",
        "no_isotp": "No ISO-TP details",
        "no_uds": "No UDS details",
        "no_session": "No session details",
        "select_evidence": "Select evidence",
        "frame_details": "Frame Details",
        "session_details": "Session",
        "evidence": "Evidence",
        "workflow": "Flash Flow",
        "expand_transfer": "Expand TransferData segments",
        "collapse_transfer": "Collapse TransferData statistics",
        "workflow_empty": "No UDS request or functional-addressing step was identified",
        "unknown_service": "Unknown service",
        "manual_review": "Manual review required",
        "manual_reason": "Manual review reason: {reason}",
        "orphan_reason": "An ECU NRC was not linked to an outstanding request; verify the real timing around the nearest same-SID request.",
        "no_rule_reason": "No rule emitted a Finding; review input quality, unsupported items, and the original trace.",
        "unsupported_reason": "{count} unsupported/unparsed records prevent an automatic conclusion.",
        "ambiguous_reason": "{count} request/response matches are ambiguous; side or timing is not unique.",
        "coverage_reason": "Input completeness: {value}; confidence for absence windows is limited.",
        "finding_title": "{id} / {layer}",
        "confidence": "Confidence: {value}",
        "side": "Side: {value}",
        "deviation": "Deviation: {value:.6f}s",
        "detected": "Detected: {value:.6f}s",
        "observed": "Observed: {value}",
        "expected": "Expected: {value}",
        "jump": "Locate",
        "show": "View",
        "frame_line": "line {line} · t={time:.6f}s · CAN ID={can_id}",
        "interval": "interval {start:.6f}s–{end:.6f}s · matched frames {count}",
        "finding_context": "Finding: {id}",
        "frame": "Frame: {value}",
        "time": "Time: {value}",
        "channel": "CH: {value}",
        "can_id": "CAN ID: {value}",
        "dlc": "DLC: {value}",
        "data": "Data: {value}",
        "direction": "Direction: {value}",
        "isotp": "ISO-TP: {value}",
        "uds": "UDS: {value}",
        "addressing": "Addressing: {value}",
        "service": "Service: {value}",
        "did": "DID: {value}",
        "did_bytes": "DID bytes: {value}",
        "did_ascii": "DID ASCII: {value}",
        "subfunction": "SubFunction: {value}",
        "subfunction_detail": "SubFunction: {value} ({description})",
        "nrc": "NRC: {value}",
        "bsc": "BSC: {value}",
        "session": "Session: {value}",
        "read_data": "Read data: {value}",
        "read_ascii": "Read ASCII: {value}",
        "write_data": "Write data: {value}",
        "write_ascii": "Write ASCII: {value}",
        "ascii": "ASCII: {value}",
        "routine_id": "RoutineID: {value}",
        "parameters": "Parameters: {value}",
        "start_address": "Start address: {value}",
        "transfer_length": "Length: {value}",
        "transfer_bytes": "Transfer bytes: {value}",
        "transfer_segments": "TransferData segments: {count} · total bytes: {bytes} · BSC: {start}–{end}",
        "raw_uds": "Raw UDS: {value}",
        "location_frame": "Frame: {value}",
        "anchor_frame": "Anchor frame: {value}",
        "location_interval": "Interval: {value:.6f}s–{value_end:.6f}s",
        "expected_role": "Expected role: {value}",
        "expected_kind": "Expected kind: {value}",
        "matched_frames": "Matched frames: {value}",
        "coverage": "Coverage complete: {value}",
        "data_label": "Data: {value}",
        "no_response": "No final response",
        "negative": "ECU negative response",
        "positive": "Positive response received",
        "functional_step": "Functional-addressing request",
        "physical": "Physical",
        "functional_addressing": "Functional",
        "status": "Status: {value}",
        "workflow_step": "Step {index} · t={time:.6f}s · {addressing} · {status}",
    },
}


def tr(key: str, language: str = "zh", **values: object) -> str:
    """Translate GUI chrome; protocol names and abbreviations stay untouched."""

    table = _TEXT.get(language, _TEXT["zh"])
    template = table.get(key, _TEXT["en"].get(key, key))
    return template.format(**values)


SERVICE_LABELS = {
    "ClearDiagnosticInformation": "清除诊断信息",
    "DiagnosticSessionControl": "诊断会话控制",
    "ECUReset": "ECU 复位",
    "ReadDTCInformation": "读取 DTC 信息",
    "ReadDataByIdentifier": "通过标识符读取数据",
    "ReadMemoryByAddress": "按地址读取内存",
    "ReadScalingDataByIdentifier": "通过标识符读取比例数据",
    "SecurityAccess": "安全访问",
    "CommunicationControl": "通信控制",
    "Authentication": "身份认证",
    "ReadDataByPeriodicIdentifier": "按周期标识符读取数据",
    "InputOutputControlByIdentifier": "通过标识符输入输出控制",
    "WriteDataByIdentifier": "通过标识符写入数据",
    "RoutineControl": "例程控制",
    "RequestDownload": "请求下载",
    "TransferData": "传输数据",
    "RequestTransferExit": "请求传输退出",
    "RequestFileTransfer": "请求文件传输",
    "WriteMemoryByAddress": "按地址写入内存",
    "TesterPresent": "测试器在线",
    "AccessTimingParameter": "访问时序参数",
    "SecuredDataTransmission": "安全数据传输",
    "ControlDTCSetting": "控制 DTC 设置",
    "ResponseOnEvent": "事件响应",
    "LinkControl": "链路控制",
}

_SESSION_LABELS = {
    "default": ("默认会话", "Default Session"),
    "programming": ("编程会话", "Programming Session"),
    "extended": ("扩展诊断会话", "Extended Diagnostic Session"),
    "safety_system": ("安全系统诊断会话", "Safety System Diagnostic Session"),
}

_SUBFUNCTION_LABELS = {
    "DiagnosticSessionControl": {
        0x01: ("默认会话", "Default Session"),
        0x02: ("编程会话", "Programming Session"),
        0x03: ("扩展诊断会话", "Extended Diagnostic Session"),
        0x04: ("安全系统诊断会话", "Safety System Diagnostic Session"),
    },
    "ECUReset": {
        0x01: ("硬复位", "Hard Reset"),
        0x02: ("钥匙关闭/打开复位", "Key Off/On Reset"),
        0x03: ("软复位", "Soft Reset"),
        0x04: ("启用快速断电", "Enable Rapid Power Shutdown"),
        0x05: ("禁用快速断电", "Disable Rapid Power Shutdown"),
    },
    "RoutineControl": {
        0x01: ("启动例程", "Start Routine"),
        0x02: ("停止例程", "Stop Routine"),
        0x03: ("请求例程结果", "Request Routine Results"),
    },
    "TesterPresent": {0x00: ("保持在线", "Tester Present")},
    "ControlDTCSetting": {
        0x01: ("开启 DTC 设置", "On"),
        0x02: ("关闭 DTC 设置", "Off"),
    },
}

_NRC_LABELS = {
    "generalReject": ("一般拒绝", "General Reject"),
    "serviceNotSupported": ("不支持该服务", "Service Not Supported"),
    "subFunctionNotSupported": ("不支持该子功能", "Sub-function Not Supported"),
    "incorrectMessageLengthOrInvalidFormat": ("消息长度错误或格式无效", "Incorrect Message Length or Invalid Format"),
    "responseTooLong": ("响应过长", "Response Too Long"),
    "busyRepeatRequest": ("忙，请重复请求", "Busy Repeat Request"),
    "conditionsNotCorrect": ("条件不正确", "Conditions Not Correct"),
    "requestSequenceError": ("请求顺序错误", "Request Sequence Error"),
    "requestOutOfRange": ("请求超出范围", "Request Out Of Range"),
    "securityAccessDenied": ("安全访问被拒绝", "Security Access Denied"),
    "invalidKey": ("密钥无效", "Invalid Key"),
    "uploadDownloadNotAccepted": ("上传/下载未接受", "Upload/Download Not Accepted"),
    "transferDataSuspended": ("数据传输已暂停", "Transfer Data Suspended"),
    "generalProgrammingFailure": ("通用编程失败", "General Programming Failure"),
    "wrongBlockSequenceCounter": ("块序列计数器错误", "Wrong Block Sequence Counter"),
    "responsePending": ("响应等待中", "Response Pending"),
}


def service_label(service_name: object, language: str = "zh") -> str:
    name = str(service_name or "").strip()
    if not name:
        return tr("unknown_service", language)
    if language == "en":
        return name
    return SERVICE_LABELS.get(name, name)


def subfunction_label(service_name: object, value: object, language: str = "zh") -> str:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)
    name = str(service_name or "")
    if name == "SecurityAccess":
        if language == "en":
            return (
                f"Request Seed (security level 0x{number:02X})"
                if number & 1
                else f"Send Key (security level 0x{number:02X})"
            )
        return (
            f"请求种子（安全等级 0x{number:02X}）"
            if number & 1
            else f"发送密钥（安全等级 0x{number:02X}）"
        )
    pair = _SUBFUNCTION_LABELS.get(name, {}).get(number)
    if pair is None:
        return f"0x{number:02X}"
    return pair[1] if language == "en" else pair[0]


def session_label(value: object, language: str = "zh") -> str:
    name = str(value or "")
    pair = _SESSION_LABELS.get(name)
    if pair is None:
        return name or "—"
    return pair[1] if language == "en" else pair[0]


def side_label(value: object, language: str = "zh") -> str:
    name = str(value or "unknown").casefold()
    if name == "ecu":
        return "ECU"
    if name == "tester":
        return "Tester"
    return "其他" if language == "zh" else "Other"


def direction_label(value: object, language: str = "zh") -> str:
    name = str(value or "other").casefold()
    if name == "tester->ecu":
        return "Tester→ECU"
    if name == "ecu->tester":
        return "ECU→Tester"
    if name == "functional":
        return "功能寻址" if language == "zh" else "Functional"
    return "其他" if language == "zh" else "Other"


def addressing_label(value: object, language: str = "zh") -> str:
    name = str(value or "unknown").casefold()
    if name == "functional":
        return "功能寻址" if language == "zh" else "Functional"
    if name == "physical":
        return "物理寻址" if language == "zh" else "Physical"
    return "未知" if language == "zh" else "Unknown"


def nrc_label(value: object, name: object = None, language: str = "zh") -> str:
    try:
        code = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(name or "—")
    canonical = str(name or "")
    pair = _NRC_LABELS.get(canonical)
    if pair is None:
        return f"0x{code:02X}"
    return f"0x{code:02X} {pair[1] if language == 'en' else pair[0]}"


def format_uds_summary(details: object, language: str = "zh", fallback: str = "") -> str:
    values = details if isinstance(details, dict) else {}
    if not values:
        return normalize_role_words(fallback, language) if fallback else ""
    sid = values.get("sid")
    if sid is None:
        return normalize_role_words(fallback, language) if fallback else ""
    try:
        sid_text = f"0x{int(sid):02X}"
    except (TypeError, ValueError):
        sid_text = str(sid)
    parts = [f"{sid_text} {service_label(values.get('service_name'), language)}"]
    if values.get("subfunction") is not None:
        number = int(values["subfunction"])
        prefix = "SubFunction" if language == "en" else "子功能"
        parts.append(f"{prefix}=0x{number:02X} ({subfunction_label(values.get('service_name'), number, language)})")
    if values.get("did") is not None:
        parts.append(f"DID=0x{int(values['did']):04X}")
    if values.get("block_seq") is not None:
        parts.append(f"BSC=0x{int(values['block_seq']):02X}")
    if values.get("nrc") is not None:
        parts.append(f"NRC={nrc_label(values.get('nrc'), values.get('nrc_name'), language)}")
    if values.get("pending"):
        parts.append("pending" if language == "en" else "等待最终响应")
    return " · ".join(parts)


def normalize_role_words(value: object, language: str = "en") -> str:
    """Normalize role spelling in legacy/raw text without changing ECU/Tester."""

    text = str(value or "")
    text = re.sub(r"(?i)(?<![A-Za-z])ecu(?![A-Za-z])", "ECU", text)
    text = re.sub(r"(?i)(?<![A-Za-z])tester(?![A-Za-z])", "Tester", text)
    return text


def evidence_summary(value: object, language: str = "zh") -> str:
    """Translate common evidence labels while preserving FF/FC/CF/BSC codes."""

    text = normalize_role_words(value, language)
    if language == "en":
        return text
    replacements = {
        "No FC observed after FF": "FF 后未观测到 FC",
        "No CF observed after CTS": "CTS 后未观测到 CF",
        "No FC observed at BS boundary": "BS 边界处未观测到 FC",
        "FF awaiting receiver flow control": "FF 等待接收方流控",
        "FF total_len=": "FF 总长度=",
        "FC FS=CTS": "FC FS=CTS",
        "last CF in block": "块内最后一个 CF",
        "last transport control/data event": "最近的传输控制/数据帧",
        "No final response before P2* deadline": "P2* 截止前未收到最终响应",
        "No final response before P2 deadline": "P2 截止前未收到最终响应",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def format_finding_text(
    finding_id: object,
    field: str,
    raw: object,
    language: str = "zh",
    *,
    detail: dict | None = None,
    service: object = None,
) -> str:
    """Render rule text in the selected language while retaining protocol codes."""

    finding = str(finding_id or "")
    values = detail or {}
    if language == "en":
        return normalize_role_words(raw, language)
    timeout = int(values.get("timeout_ms", 0) or 0)
    if finding == "ISO-TP-001":
        return "FF 后未在配置超时时间内收到 FC" if field == "observed" else f"FC 应在 {timeout} ms 内到达"
    if finding == "ISO-TP-002":
        return "CTS 后未在配置超时时间内收到 CF" if field == "observed" else f"CF 应在 {timeout} ms 内到达"
    if finding == "ISO-TP-003":
        return f"收到的 CF 序号：{raw}" if field == "observed" else f"期望 CF 序号：{raw}"
    if finding == "ISO-TP-004":
        return "BS 边界后未及时收到 FC" if field == "observed" else f"BS 边界后应在 {timeout} ms 内收到下一个 FC"
    if finding == "ISO-TP-005":
        return f"CF 间隔：{raw}" if field == "observed" else f"CF 间隔应满足：{raw}"
    if finding == "UDS-001":
        return "在 P2/P2* 超时前未收到最终 UDS 响应" if field == "observed" else f"应在 {timeout} ms 内收到最终 UDS 响应"
    if finding == "UDS-002":
        if field == "observed":
            code = values.get("nrc")
            return f"ECU 返回 {nrc_label(code, values.get('nrc_name'), language)}" if code is not None else "ECU 返回格式错误的负响应"
        return f"服务 {service_label(service or values.get('service'), language)} 应返回正响应"
    if finding == "FLASH-001":
        if values.get("violations") and "oversize" in values.get("violations", []):
            if field == "observed":
                return f"TransferData 请求长度：{values.get('request_length', raw)}"
            return f"TransferData 请求长度应 ≤ {values.get('max_block_length', raw)}"
        if field == "observed":
            return f"块序列计数器：{values.get('block_seq', raw)}"
        return f"期望块序列计数器：{values.get('expected_block_seq', raw)}"
    return normalize_role_words(raw, language)


__all__ = [
    "LANGUAGE_CODES",
    "LANGUAGE_LABELS",
    "addressing_label",
    "direction_label",
    "evidence_summary",
    "format_finding_text",
    "format_uds_summary",
    "nrc_label",
    "normalize_role_words",
    "service_label",
    "session_label",
    "side_label",
    "subfunction_label",
    "tr",
]
