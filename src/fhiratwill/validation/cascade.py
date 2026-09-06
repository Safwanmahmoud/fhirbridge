"""Orchestration for the honest eight-layer validation cascade."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from fhiratwill.terminology import TerminologyClient
from fhiratwill.validation.adapters import ValidatorClient
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
from fhiratwill.validation.plausibility import validate_plausibility
from fhiratwill.validation.structural import validate_structure
from fhiratwill.validation.terminology import validate_terminology
from fhiratwill.validation.validator_layers import validate_invariants, validate_profile

_NO_VALIDATOR = "No ValidatorClient adapter was supplied; this blocking layer did not run."
_NO_TERMINOLOGY = "No TerminologyClient adapter was supplied; this blocking layer did not run."
_NO_SOURCE = (
    "Standalone validation has no source document or spans, so this comparison is not applicable."
)


async def validate(
    resource: object,
    *,
    validator: ValidatorClient | None = None,
    terminology: TerminologyClient | None = None,
    config: ValidationConfig | None = None,
    spec: ValidationSpec | None = None,
) -> ValidationReport:
    settings = config or ValidationConfig()
    request = spec or ValidationSpec()
    started = time.perf_counter()
    structural = validate_structure(resource)
    layers: dict[ValidationLayer, LayerResult] = {ValidationLayer.STRUCTURAL: structural.result}
    body: dict[str, Any] = resource if isinstance(resource, dict) else {}
    resource_type = structural.resource_type or "Unknown"
    usable = (
        isinstance(resource, dict)
        and structural.resource_type is not None
        and not any(issue.severity is IssueSeverity.FATAL for issue in structural.result.issues)
    )

    if not usable:
        reason = "L1 could not identify a FHIR resource, so this layer could not run."
        layers[ValidationLayer.PROFILE] = _skip(ValidationLayer.PROFILE, reason)
        layers[ValidationLayer.TERMINOLOGY] = _skip(ValidationLayer.TERMINOLOGY, reason)
        layers[ValidationLayer.INVARIANTS] = _skip(ValidationLayer.INVARIANTS, reason)
    else:
        layers[ValidationLayer.PROFILE] = await _profile(body, validator, request)
        layers[ValidationLayer.TERMINOLOGY] = await _terminology(
            body, terminology, request, settings
        )
        layers[ValidationLayer.INVARIANTS] = await _invariants(
            body, resource_type, validator, request, settings
        )

    # L5 is intentionally local and always runs, including after L1 failure.
    layers[ValidationLayer.PLAUSIBILITY] = validate_plausibility(
        resource,
        resource_type=structural.resource_type,
        expected_version=settings.plausibility_pack_version,
        severity_overrides=request.severity_overrides,
    )
    for layer in (ValidationLayer.FIDELITY, ValidationLayer.COVERAGE):
        layers[layer] = LayerResult(
            layer=layer,
            layer_number=layer.number,
            status=LayerStatus.NOT_APPLICABLE,
            blocking=False,
            skipped_reason=_NO_SOURCE,
        )
    return _assemble(
        layers,
        resource_type,
        structural.resource_count,
        settings,
        request,
        started,
    )


async def _profile(
    body: dict[str, Any], validator: ValidatorClient | None, request: ValidationSpec
) -> LayerResult:
    if not request.wants(ValidationLayer.PROFILE):
        return _skip(ValidationLayer.PROFILE, "Not requested by the caller.")
    if validator is None:
        return _skip(ValidationLayer.PROFILE, _NO_VALIDATOR)
    return await validate_profile(body, client=validator, profiles=request.profiles)


async def _terminology(
    body: dict[str, Any],
    terminology: TerminologyClient | None,
    request: ValidationSpec,
    settings: ValidationConfig,
) -> LayerResult:
    if not request.wants(ValidationLayer.TERMINOLOGY):
        return _skip(ValidationLayer.TERMINOLOGY, "Not requested by the caller.")
    if terminology is None:
        return _skip(ValidationLayer.TERMINOLOGY, _NO_TERMINOLOGY)
    return await validate_terminology(
        body,
        client=terminology,
        expected_version=settings.binding_table_version,
        max_checks=request.max_terminology_checks,
    )


async def _invariants(
    body: dict[str, Any],
    resource_type: str,
    validator: ValidatorClient | None,
    request: ValidationSpec,
    settings: ValidationConfig,
) -> LayerResult:
    if not request.wants(ValidationLayer.INVARIANTS):
        return _skip(ValidationLayer.INVARIANTS, "Not requested by the caller.")
    if validator is None:
        return _skip(ValidationLayer.INVARIANTS, _NO_VALIDATOR)
    return await validate_invariants(
        body,
        client=validator,
        resource_type=resource_type,
        expected_version=settings.invariant_pack_version,
    )


def _assemble(
    mapping: dict[ValidationLayer, LayerResult],
    resource_type: str,
    resource_count: int,
    config: ValidationConfig,
    spec: ValidationSpec,
    started: float,
) -> ValidationReport:
    ordered = [mapping[layer] for layer in CASCADE_ORDER if layer is not ValidationLayer.ROUTING]
    blocking = [
        issue
        for result in ordered
        if result.blocking
        for issue in result.issues
        if issue.severity.is_blocking
    ]
    warnings = [
        issue
        for result in ordered
        for issue in result.issues
        if issue.severity is IssueSeverity.WARNING
    ]
    skipped = [
        result for result in ordered if result.blocking and result.status is LayerStatus.SKIPPED
    ]
    critical = _critical_flags(ordered)
    if blocking:
        decision = RoutingDecision.REJECT
    elif skipped or warnings or critical:
        decision = RoutingDecision.NEEDS_REVIEW
    else:
        decision = RoutingDecision.AUTO
    routing = LayerResult(
        layer=ValidationLayer.ROUTING,
        layer_number=8,
        status=LayerStatus.PASSED,
        blocking=False,
        issues=[
            ValidationIssue(
                layer=ValidationLayer.ROUTING,
                severity=IssueSeverity.INFORMATION,
                code="informational",
                message=_rationale(decision, blocking, skipped),
            )
        ],
    )
    return ValidationReport(
        status=decision,
        conformant=not blocking and not skipped,
        resource_type=resource_type,
        resource_count=resource_count,
        layers=[*ordered, routing],
        scores=ValidationScores(conformance=None if skipped else (0.0 if blocking else 1.0)),
        critical_flags=critical,
        versions=ReportVersions(
            code=config.code_version,
            report_schema=config.report_schema_version,
            fhir=config.fhir_version,
            typed_models=config.typed_model_fhir_version,
            binding_table=str(config.binding_table_version),
            invariant_pack=str(config.invariant_pack_version),
            plausibility_pack=str(config.plausibility_pack_version),
            ig=list(spec.ig_packages),
            validator=config.validator_version,
            terminology=dict(config.terminology_versions),
        ),
        conversion_id=spec.conversion_id,
        profiles=list(spec.profiles),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _skip(layer: ValidationLayer, reason: str) -> LayerResult:
    return LayerResult(
        layer=layer,
        layer_number=layer.number,
        status=LayerStatus.SKIPPED,
        blocking=True,
        skipped_reason=reason,
    )


def _critical_flags(results: Sequence[LayerResult]) -> list[CriticalFlag]:
    flags: list[CriticalFlag] = []
    domains = {
        "allergy": ("AllergyIntolerance",),
        "medication_dose": ("dosage", "doseQuantity", "doseRange", "rateQuantity"),
        "laterality": ("bodySite", "laterality"),
    }
    seen: set[tuple[str, str]] = set()
    for result in results:
        for issue in result.issues:
            expression = issue.expression or ""
            for domain, markers in domains.items():
                if (
                    any(marker in expression for marker in markers)
                    and (domain, expression) not in seen
                ):
                    seen.add((domain, expression))
                    flags.append(
                        CriticalFlag(
                            domain=domain,
                            reason=f"{result.layer} reported an issue in a critical domain",
                            expression=issue.expression,
                        )
                    )
    return flags


def _rationale(
    decision: RoutingDecision,
    blocking: Sequence[ValidationIssue],
    skipped: Sequence[LayerResult],
) -> str:
    if decision is RoutingDecision.REJECT:
        return f"Rejected because {len(blocking)} blocking issue(s) were found."
    if decision is RoutingDecision.NEEDS_REVIEW:
        return (
            "Needs review because blocking layers did not run or non-blocking concerns "
            f"remain ({len(skipped)} blocking layer skip(s))."
        )
    return "All applicable layers ran without blocking issues or warnings."


__all__ = ["validate"]
