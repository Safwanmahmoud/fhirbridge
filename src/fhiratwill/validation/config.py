"""Configuration and request specification for validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from fhiratwill.validation.models import ValidationLayer


@dataclass(frozen=True, slots=True)
class ValidationConfig:
    fhir_version: str = "4.0.1"
    typed_model_fhir_version: str = "4.3.0"
    code_version: str = "0.2.0"
    report_schema_version: str = "1"
    binding_table_version: int = 1
    invariant_pack_version: int = 1
    plausibility_pack_version: int = 1
    validator_version: str | None = None
    terminology_versions: Mapping[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ValidationSpec:
    profiles: tuple[str, ...] = ()
    layers: frozenset[ValidationLayer] | None = None
    severity_overrides: Mapping[str, str] = field(default_factory=dict)
    max_terminology_checks: int = 250
    conversion_id: str | None = None
    ig_packages: tuple[str, ...] = ()

    def wants(self, layer: ValidationLayer) -> bool:
        return self.layers is None or layer in self.layers


__all__ = ["ValidationConfig", "ValidationSpec"]
