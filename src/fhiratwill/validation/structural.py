"""L1 structural validation using the packaged fhir.resources R4B models."""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from fhiratwill.validation.models import (
    IssueSeverity,
    LayerResult,
    LayerStatus,
    ValidationIssue,
    ValidationLayer,
)

_R4B_ONLY = frozenset(
    {
        "AdministrableProductDefinition",
        "Citation",
        "ClinicalUseDefinition",
        "Ingredient",
        "ManufacturedItemDefinition",
        "MedicinalProductDefinition",
        "NutritionProduct",
        "PackagedProductDefinition",
        "RegulatedAuthorization",
        "SubscriptionStatus",
        "SubscriptionTopic",
    }
)
_ABSTRACT = frozenset({"Resource", "DomainResource"})
_R4_WITHOUT_MODELS = frozenset(
    {
        "EffectEvidenceSynthesis",
        "MedicinalProduct",
        "MedicinalProductAuthorization",
        "MedicinalProductContraindication",
        "MedicinalProductIndication",
        "MedicinalProductIngredient",
        "MedicinalProductInteraction",
        "MedicinalProductManufactured",
        "MedicinalProductPackaged",
        "MedicinalProductPharmaceutical",
        "MedicinalProductUndesirableEffect",
        "RiskEvidenceSynthesis",
        "SubstanceNucleicAcid",
        "SubstancePolymer",
        "SubstanceProtein",
        "SubstanceReferenceInformation",
        "SubstanceSourceMaterial",
        "SubstanceSpecification",
    }
)


@dataclass(slots=True)
class StructuralResult:
    result: LayerResult
    typed: Any | None
    resource_type: str | None
    resource_count: int


def _model_for(resource_type: str) -> type[Any] | None:
    try:
        module = importlib.import_module(f"fhir.resources.R4B.{resource_type.lower()}")
    except ModuleNotFoundError:
        return None
    model = getattr(module, resource_type, None)
    return model if isinstance(model, type) else None


def validate_structure(payload: object) -> StructuralResult:
    started = time.perf_counter()
    issues: list[ValidationIssue] = []
    notes: list[str] = []
    typed: Any | None = None
    resource_type: str | None = None
    count = 0
    if not isinstance(payload, dict):
        issues.append(_issue(IssueSeverity.FATAL, "structure", "Payload must be a JSON object."))
    else:
        raw_type = payload.get("resourceType")
        if not isinstance(raw_type, str) or not raw_type:
            issues.append(
                _issue(
                    IssueSeverity.FATAL,
                    "structure",
                    "Payload has no resourceType and is not a FHIR resource.",
                    "$this.resourceType",
                )
            )
        else:
            resource_type = raw_type
            count = _resource_count(payload, raw_type)
            if raw_type in _R4B_ONLY or raw_type in _ABSTRACT:
                issues.append(
                    _issue(
                        IssueSeverity.FATAL,
                        "not-supported",
                        "resourceType is not an instantiable FHIR R4 resource type.",
                        "$this.resourceType",
                    )
                )
            else:
                model = _model_for(raw_type)
                if model is None and raw_type not in _R4_WITHOUT_MODELS:
                    resource_type = None
                    count = 0
                    issues.append(
                        _issue(
                            IssueSeverity.FATAL,
                            "not-supported",
                            "resourceType is not a supported FHIR R4 resource type.",
                            "$this.resourceType",
                        )
                    )
                elif model is None:
                    issues.append(
                        _issue(
                            IssueSeverity.WARNING,
                            "incomplete",
                            "No typed model is available; L2 must establish conformance.",
                            "$this.resourceType",
                        )
                    )
                    notes.append("L1 did not type-check this resource; conformance rests on L2.")
                else:
                    try:
                        typed = model.model_validate(payload)
                    except ValidationError as exc:
                        for error in exc.errors()[:200]:
                            issues.append(
                                _issue(
                                    IssueSeverity.ERROR,
                                    "required" if "missing" in str(error["type"]) else "structure",
                                    "Typed FHIR model validation failed.",
                                    raw_type,
                                )
                            )
                    except ValueError:
                        issues.append(
                            _issue(
                                IssueSeverity.FATAL,
                                "structure",
                                "The resource could not be parsed as FHIR R4.",
                            )
                        )
    result = LayerResult(
        layer=ValidationLayer.STRUCTURAL,
        layer_number=1,
        status=LayerStatus.FAILED
        if any(issue.severity.is_blocking for issue in issues)
        else LayerStatus.PASSED,
        blocking=True,
        issues=issues,
        notes=notes,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return StructuralResult(result, typed, resource_type, count)


def _resource_count(payload: dict[str, Any], resource_type: str) -> int:
    if resource_type != "Bundle":
        return 1
    entries = payload.get("entry")
    return (
        sum(
            isinstance(entry, dict) and isinstance(entry.get("resource"), dict) for entry in entries
        )
        if isinstance(entries, list)
        else 0
    )


def _issue(
    severity: IssueSeverity, code: str, message: str, expression: str | None = None
) -> ValidationIssue:
    return ValidationIssue(
        layer=ValidationLayer.STRUCTURAL,
        severity=severity,
        code=code,
        message=message,
        expression=expression,
    )


__all__ = ["StructuralResult", "validate_structure"]
