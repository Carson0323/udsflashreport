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
    AnalysisResult,
    AppConfig,
    ConfigValidationResult,
    TraceBundle,
)


def validate_config(data: dict) -> ConfigValidationResult:
    return validate_config_data(data)


def load_trace(path: str, cfg: AppConfig) -> TraceBundle:
    raise NotImplementedError("trace loading is scheduled for M1")


def analyze_trace(bundle: TraceBundle, cfg: AppConfig) -> AnalysisResult:
    raise NotImplementedError("trace analysis is scheduled for M2-M4")


def export_report(result: AnalysisResult, md_path: str | None, json_path: str | None) -> dict:
    raise NotImplementedError("report export is scheduled for M5")


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

