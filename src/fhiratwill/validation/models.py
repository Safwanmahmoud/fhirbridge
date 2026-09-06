"""Stable, PHI-safe value models for the eight-layer validation report."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ValidationLayer(StrEnum):
    STRUCTURAL = "structural"
    PROFILE = "profile"
    TERMINOLOGY = "terminology"
    INVARIANTS = "invariants"
    PLAUSIBILITY = "plausibility"
    FIDELITY = "fidelity"
    COVERAGE = "coverage"
    ROUTING = "routing"

    @property
    def number(self) -> int:
        return tuple(ValidationLayer).index(self) + 1


CASCADE_ORDER = tuple(ValidationLayer)


class IssueSeverity(StrEnum):
    FATAL = "fatal"
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"

    @property
    def is_blocking(self) -> bool:
        return self in {self.FATAL, self.ERROR}


class LayerStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_APPLICABLE = "not_applicable"


class RoutingDecision(StrEnum):
    AUTO = "auto"
    NEEDS_REVIEW = "needs_review"
    REJECT = "reject"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    layer: ValidationLayer
    severity: IssueSeverity
    code: str
    message: str
    expression: str | None = None
    rule_id: str | None = None
    machine_code: str | None = None
    line: int | None = None
    column: int | None = None


class LayerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: ValidationLayer
    layer_number: int
    status: LayerStatus
    blocking: bool
    errors: int = 0
    warnings: int = 0
    informational: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)
    duration_ms: int = 0
    skipped_reason: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _count_issues(self) -> Self:
        self.errors = sum(issue.severity.is_blocking for issue in self.issues)
        self.warnings = sum(issue.severity is IssueSeverity.WARNING for issue in self.issues)
        self.informational = sum(
            issue.severity is IssueSeverity.INFORMATION for issue in self.issues
        )
        return self


class ValidationScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conformance: Annotated[float, Field(ge=0, le=1)] | None = None
    fidelity: Annotated[float, Field(ge=0, le=1)] | None = None
    coverage: Annotated[float, Field(ge=0, le=1)] | None = None
    mean_confidence: Annotated[float, Field(ge=0, le=1)] | None = None


class CriticalFlag(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: str
    reason: str
    fact_id: str | None = None
    expression: str | None = None


class ReportVersions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    report_schema: str
    fhir: str
    typed_models: str
    binding_table: str
    invariant_pack: str
    plausibility_pack: str
    ig: list[str] = Field(default_factory=list)
    validator: str | None = None
    terminology: dict[str, str | None] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RoutingDecision
    conformant: bool
    resource_type: str
    resource_count: int
    layers: list[LayerResult]
    scores: ValidationScores = Field(default_factory=ValidationScores)
    critical_flags: list[CriticalFlag] = Field(default_factory=list)
    omissions: list[dict[str, object]] = Field(default_factory=list)
    versions: ReportVersions
    nondeterminism_risk: bool = False
    nondeterminism_reasons: list[str] = Field(default_factory=list)
    conversion_id: str | None = None
    validated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    profiles: list[str] = Field(default_factory=list)
    duration_ms: int = 0

    @property
    def blocking_issues(self) -> list[ValidationIssue]:
        return [
            issue
            for result in self.layers
            if result.blocking
            for issue in result.issues
            if issue.severity.is_blocking
        ]

    def layer(self, layer: ValidationLayer) -> LayerResult | None:
        return next((result for result in self.layers if result.layer is layer), None)


__all__ = [
    "CASCADE_ORDER",
    "CriticalFlag",
    "IssueSeverity",
    "LayerResult",
    "LayerStatus",
    "ReportVersions",
    "RoutingDecision",
    "ValidationIssue",
    "ValidationLayer",
    "ValidationReport",
    "ValidationScores",
]
