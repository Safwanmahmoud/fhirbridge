"""Typed public values for deterministic narrative de-identification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class DeidMode(StrEnum):
    OFF = "off"
    ADVISORY = "advisory"
    ENFORCED = "enforced"


class DeidProfile(StrEnum):
    HIPAA_SAFE_HARBOR = "hipaa_safe_harbor"
    HIPAA_LIMITED_DATA_SET = "hipaa_limited_data_set"


class IdentifierClass(StrEnum):
    NAME = "name"
    DATE = "date"
    AGE = "age"
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"
    LOCATION = "location"
    ZIP = "zip"
    SSN = "ssn"
    MRN = "mrn"
    ACCOUNT = "account"
    LICENSE = "license"
    DEVICE = "device"
    URL = "url"
    IP = "ip"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class DeclaredIdentifier:
    identifier_class: IdentifierClass
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("declared identifier must not be empty")


@dataclass(frozen=True, slots=True)
class DeidPolicy:
    mode: DeidMode = DeidMode.ENFORCED
    profile: DeidProfile = DeidProfile.HIPAA_SAFE_HARBOR

    @property
    def enabled(self) -> bool:
        return self.mode is not DeidMode.OFF

    @property
    def enforced(self) -> bool:
        return self.mode is DeidMode.ENFORCED


@dataclass(frozen=True, slots=True)
class DeidentifyResult:
    """The body may contain clinical text; notes and counts never do."""

    text: str
    mode: DeidMode
    profile: DeidProfile
    ruleset_version: str
    detections: dict[str, int] = field(default_factory=dict)
    replacements: int = 0
    notes: tuple[str, ...] = ()


@runtime_checkable
class DeidObserver(Protocol):
    """Receives bounded counts only—never narrative or identifier values."""

    def observe(
        self,
        *,
        mode: DeidMode,
        detections: Mapping[str, int],
        replacements: int,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class NoOpDeidObserver:
    def observe(
        self,
        *,
        mode: DeidMode,
        detections: Mapping[str, int],
        replacements: int,
    ) -> None:
        del mode, detections, replacements


NOOP_DEID_OBSERVER = NoOpDeidObserver()


__all__ = [
    "NOOP_DEID_OBSERVER",
    "DeclaredIdentifier",
    "DeidMode",
    "DeidObserver",
    "DeidPolicy",
    "DeidProfile",
    "DeidentifyResult",
    "IdentifierClass",
    "NoOpDeidObserver",
]
