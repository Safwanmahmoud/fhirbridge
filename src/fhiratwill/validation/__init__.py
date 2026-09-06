"""Decoupled eight-layer FHIR validation."""

from fhiratwill.validation.adapters import (
    FhirPathOutcome,
    IgNotLoadedError,
    ValidatorClient,
    ValidatorIssue,
    ValidatorOutcome,
    ValidatorUnavailableError,
)
from fhiratwill.validation.cascade import validate
from fhiratwill.validation.config import ValidationConfig, ValidationSpec
from fhiratwill.validation.models import (
    CASCADE_ORDER,
    CriticalFlag,
    IssueSeverity,
    LayerResult,
    LayerStatus,
    ReportVersions,
    RoutingDecision,
    ValidationIssue,
    ValidationLayer,
    ValidationReport,
    ValidationScores,
)

__all__ = [
    "CASCADE_ORDER",
    "CriticalFlag",
    "FhirPathOutcome",
    "IgNotLoadedError",
    "IssueSeverity",
    "LayerResult",
    "LayerStatus",
    "ReportVersions",
    "RoutingDecision",
    "ValidationConfig",
    "ValidationIssue",
    "ValidationLayer",
    "ValidationReport",
    "ValidationScores",
    "ValidationSpec",
    "ValidatorClient",
    "ValidatorIssue",
    "ValidatorOutcome",
    "ValidatorUnavailableError",
    "validate",
]
