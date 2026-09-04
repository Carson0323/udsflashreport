from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    AddressingConfig,
    AppConfig,
    ConfigValidationResult,
    IsoTpConfig,
    ManualPair,
    RulesConfig,
    RULE_CONFIG_KEYS,
    TimeoutsConfig,
)


_TOP_LEVEL_KEYS = {"schema_version", "addressing", "isotp", "timeouts", "rules"}
_ADDRESSING_KEYS = {
    "auto_detect",
    "tester_sa",
    "enable_11bit_heuristic",
    "enable_29bit_normal_fixed",
    "manual_pairs",
}
_ISOTP_KEYS = {"addressing_mode"}
_TIMEOUT_KEYS = {"isotp_fc_ms", "isotp_cf_ms", "uds_p2_ms", "uds_p2_star_ms"}
_RULE_KEYS = set(RULE_CONFIG_KEYS.values())


def _type_error(path: str, expected: str) -> str:
    return f"{path}: expected {expected}"


def validate_config_data(data: dict[str, Any]) -> ConfigValidationResult:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ConfigValidationResult(ok=False, errors=["root: expected object"])

    missing = _TOP_LEVEL_KEYS - data.keys()
    unknown = data.keys() - _TOP_LEVEL_KEYS
    errors.extend(f"root: missing required field {key}" for key in sorted(missing))
    errors.extend(f"root: unknown field {key}" for key in sorted(unknown))

    if data.get("schema_version") != "1.2":
        errors.append("schema_version: must be '1.2'")

    addressing = data.get("addressing")
    if not isinstance(addressing, dict):
        errors.append(_type_error("addressing", "object"))
    else:
        errors.extend(
            f"addressing: unknown field {key}"
            for key in sorted(addressing.keys() - _ADDRESSING_KEYS)
        )
        errors.extend(
            f"addressing: missing required field {key}"
            for key in sorted(_ADDRESSING_KEYS - addressing.keys())
        )
        for key in (
            "auto_detect",
            "enable_11bit_heuristic",
            "enable_29bit_normal_fixed",
        ):
            if key in addressing and not isinstance(addressing[key], bool):
                errors.append(_type_error(f"addressing.{key}", "boolean"))
        if "tester_sa" in addressing and not isinstance(addressing["tester_sa"], str):
            errors.append(_type_error("addressing.tester_sa", "string"))
        manual_pairs = addressing.get("manual_pairs")
        if not isinstance(manual_pairs, list):
            errors.append(_type_error("addressing.manual_pairs", "array"))
        else:
            for index, pair in enumerate(manual_pairs):
                path = f"addressing.manual_pairs[{index}]"
                if not isinstance(pair, dict):
                    errors.append(_type_error(path, "object"))
                    continue
                required = {"name", "request_id", "response_id", "channel", "is_extended_id"}
                errors.extend(
                    f"{path}: missing required field {key}"
                    for key in sorted(required - pair.keys())
                )
                errors.extend(
                    f"{path}: unknown field {key}"
                    for key in sorted(pair.keys() - required)
                )
                for key in ("name", "request_id", "response_id"):
                    if key in pair and not isinstance(pair[key], str):
                        errors.append(_type_error(f"{path}.{key}", "string"))
                if "is_extended_id" in pair and not isinstance(pair["is_extended_id"], bool):
                    errors.append(_type_error(f"{path}.is_extended_id", "boolean"))
                channel = pair.get("channel")
                if channel is not None and not isinstance(channel, (int, str)):
                    errors.append(_type_error(f"{path}.channel", "integer, string, or null"))

    isotp = data.get("isotp")
    if not isinstance(isotp, dict):
        errors.append(_type_error("isotp", "object"))
    else:
        errors.extend(f"isotp: unknown field {key}" for key in sorted(isotp.keys() - _ISOTP_KEYS))
        errors.extend(
            f"isotp: missing required field {key}" for key in sorted(_ISOTP_KEYS - isotp.keys())
        )
        if isotp.get("addressing_mode") not in {"auto", "normal", "extended", "mixed"}:
            errors.append("isotp.addressing_mode: invalid value")

    timeouts = data.get("timeouts")
    if not isinstance(timeouts, dict):
        errors.append(_type_error("timeouts", "object"))
    else:
        errors.extend(f"timeouts: unknown field {key}" for key in sorted(timeouts.keys() - _TIMEOUT_KEYS))
        errors.extend(
            f"timeouts: missing required field {key}" for key in sorted(_TIMEOUT_KEYS - timeouts.keys())
        )
        for key in _TIMEOUT_KEYS:
            value = timeouts.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(_type_error(f"timeouts.{key}", "non-negative integer"))

    rules = data.get("rules")
    if not isinstance(rules, dict):
        errors.append(_type_error("rules", "object"))
    else:
        errors.extend(f"rules: unknown field {key}" for key in sorted(rules.keys() - _RULE_KEYS))
        errors.extend(f"rules: missing required field {key}" for key in sorted(_RULE_KEYS - rules.keys()))
        for key in _RULE_KEYS:
            if key in rules and not isinstance(rules[key], bool):
                errors.append(_type_error(f"rules.{key}", "boolean"))

    return ConfigValidationResult(ok=not errors, errors=errors)


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "schema_version": config.schema_version,
        "addressing": {
            "auto_detect": config.addressing.auto_detect,
            "tester_sa": config.addressing.tester_sa,
            "enable_11bit_heuristic": config.addressing.enable_11bit_heuristic,
            "enable_29bit_normal_fixed": config.addressing.enable_29bit_normal_fixed,
            "manual_pairs": [
                {
                    "name": pair.name,
                    "request_id": pair.request_id,
                    "response_id": pair.response_id,
                    "channel": pair.channel,
                    "is_extended_id": pair.is_extended_id,
                }
                for pair in config.addressing.manual_pairs
            ],
        },
        "isotp": {"addressing_mode": config.isotp.addressing_mode},
        "timeouts": {
            "isotp_fc_ms": config.timeouts.isotp_fc_ms,
            "isotp_cf_ms": config.timeouts.isotp_cf_ms,
            "uds_p2_ms": config.timeouts.uds_p2_ms,
            "uds_p2_star_ms": config.timeouts.uds_p2_star_ms,
        },
        "rules": {
            RULE_CONFIG_KEYS[field_name]: getattr(config.rules, field_name)
            for field_name in RULE_CONFIG_KEYS
        },
    }


def config_from_dict(data: dict[str, Any]) -> AppConfig:
    result = validate_config_data(data)
    if not result.ok:
        raise ValueError("invalid configuration: " + "; ".join(result.errors))

    addressing = data["addressing"]
    pairs = tuple(
        ManualPair(
            name=pair["name"],
            request_id=pair["request_id"],
            response_id=pair["response_id"],
            channel=pair["channel"],
            is_extended_id=pair["is_extended_id"],
        )
        for pair in addressing["manual_pairs"]
    )
    reverse_rule_keys = {value: key for key, value in RULE_CONFIG_KEYS.items()}
    rules = RulesConfig(
        **{field_name: data["rules"][json_key] for json_key, field_name in reverse_rule_keys.items()}
    )
    return AppConfig(
        schema_version=data["schema_version"],
        addressing=AddressingConfig(
            auto_detect=addressing["auto_detect"],
            tester_sa=addressing["tester_sa"],
            enable_11bit_heuristic=addressing["enable_11bit_heuristic"],
            enable_29bit_normal_fixed=addressing["enable_29bit_normal_fixed"],
            manual_pairs=pairs,
        ),
        isotp=IsoTpConfig(addressing_mode=data["isotp"]["addressing_mode"]),
        timeouts=TimeoutsConfig(**data["timeouts"]),
        rules=rules,
    )


def default_config() -> AppConfig:
    return AppConfig()


def load_config(path: str | None = None) -> AppConfig:
    if path is None:
        return default_config()
    with Path(path).open("r", encoding="utf-8") as handle:
        return config_from_dict(json.load(handle))


def save_config(config: AppConfig, path: str) -> None:
    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(config_to_dict(config), handle, ensure_ascii=False, indent=2)
        handle.write("\n")

