"""Version-checked loading of packaged validation rule artifacts."""

from __future__ import annotations

from importlib.resources import files
from typing import Any

import yaml


def load_rule_yaml(name: str, *, expected_version: int) -> dict[str, Any]:
    resource = files("fhiratwill.validation").joinpath("rules", name)
    raw = yaml.safe_load(resource.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must contain a YAML mapping")
    actual = raw.get("version")
    if actual != expected_version:
        raise ValueError(f"{name} version mismatch: expected {expected_version}, found {actual!r}")
    return raw


__all__ = ["load_rule_yaml"]
