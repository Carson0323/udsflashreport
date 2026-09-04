from __future__ import annotations

import json
from pathlib import Path

from flashreport_core.api import default_config, validate_config
from flashreport_core.config import config_from_dict, config_to_dict


ROOT = Path(__file__).resolve().parents[1]


def test_config_schema_is_valid_json_and_has_frozen_contract() -> None:
    schema = json.loads((ROOT / "spec" / "config.schema.json").read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("draft/2020-12/schema")
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == "1.2"
    assert set(schema["properties"]["rules"]["required"]) == {
        "ISO-TP-001",
        "ISO-TP-002",
        "ISO-TP-003",
        "ISO-TP-004",
        "ISO-TP-005",
        "UDS-001",
        "FLASH-001",
    }


def test_default_config_round_trips_and_validates() -> None:
    original = default_config()
    data = config_to_dict(original)
    assert validate_config(data).ok
    assert config_from_dict(data) == original


def test_unknown_config_field_is_rejected() -> None:
    data = config_to_dict(default_config())
    data["unexpected"] = True
    result = validate_config(data)
    assert not result.ok
    assert any("unknown field unexpected" in error for error in result.errors)

