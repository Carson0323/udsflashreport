from __future__ import annotations

"""The deliberately small UDS service and NRC vocabulary for v1."""


SERVICE_NAMES: dict[int, str] = {
    0x10: "DiagnosticSessionControl",
    0x11: "ECUReset",
    0x22: "ReadDataByIdentifier",
    0x27: "SecurityAccess",
    0x2E: "WriteDataByIdentifier",
    0x31: "RoutineControl",
    0x34: "RequestDownload",
    0x36: "TransferData",
    0x37: "RequestTransferExit",
    0x3E: "TesterPresent",
}

POSITIVE_SERVICE_NAMES = {sid + 0x40: name for sid, name in SERVICE_NAMES.items()}

NRC_NAMES: dict[int, str] = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x14: "responseTooLong",
    0x21: "busyRepeatRequest",
    0x22: "conditionsNotCorrect",
    0x24: "requestSequenceError",
    0x26: "failurePreventsExecutionOfRequestedAction",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceedNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x70: "uploadDownloadNotAccepted",
    0x71: "transferDataSuspended",
    0x72: "generalProgrammingFailure",
    0x73: "wrongBlockSequenceCounter",
    0x78: "responsePending",
    0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
}


SUBFUNCTION_SERVICES = {0x10, 0x11, 0x27, 0x31, 0x3E}


def service_name(sid: int | None) -> str | None:
    if sid is None:
        return None
    if sid == 0x7F:
        return None
    return SERVICE_NAMES.get(sid) or POSITIVE_SERVICE_NAMES.get(sid)


def base_service_sid(sid: int | None, raw: bytes = b"") -> int | None:
    if sid is None:
        return None
    if sid == 0x7F:
        return raw[1] if len(raw) >= 2 else None
    return sid - 0x40 if sid in POSITIVE_SERVICE_NAMES else sid


def nrc_name(code: int | None) -> str | None:
    if code is None:
        return None
    return NRC_NAMES.get(code, f"unknownNRC_0x{code:02X}")


__all__ = [
    "NRC_NAMES",
    "POSITIVE_SERVICE_NAMES",
    "SERVICE_NAMES",
    "SUBFUNCTION_SERVICES",
    "base_service_sid",
    "nrc_name",
    "service_name",
]
