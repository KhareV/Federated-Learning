"""Configuration loading with narrow T001 structural validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML mapping; reject empty or non-mapping documents."""
    with Path(path).open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return value


def validate_base_config(config: dict[str, Any]) -> None:
    """Validate locked identifiers without asserting hardware semantics."""
    expected = {
        ("project", "spec_version"): "2.2",
        ("project", "current_phase"): "T011",
        ("project", "clinical_status"): "research_prototype",
        ("versions", "target"): "AAMI_SVF_WINDOW_V1",
        ("versions", "label_map"): "AAMI_SVF_MAP_V1",
        ("versions", "wearable_dataset"): "WEARABLE_V1",
        ("reproducibility", "hash_algorithm"): "sha256",
        ("reproducibility", "timezone"): "UTC",
    }
    for keys, required_value in expected.items():
        section, field = keys
        actual = config.get(section, {}).get(field)
        if actual != required_value:
            raise ValueError(f"{section}.{field} must be {required_value!r}, got {actual!r}")
