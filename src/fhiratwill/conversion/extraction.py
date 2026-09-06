"""Strict catalog-constrained extraction schema."""

from __future__ import annotations

import re
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, field_validator

from fhiratwill.conversion.errors import ExtractionSchemaError

MAX_EXTRACTED_ENTITIES: Final = 500
_INSTANCE_SLUG: Final = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

RESOURCE_CATALOG: Final[dict[str, frozenset[str]]] = {
    "AllergyIntolerance": frozenset(
        {"category", "clinicalStatus", "code", "criticality", "patient", "reaction", "type"}
    ),
    "CarePlan": frozenset(
        {"activity", "addresses", "category", "encounter", "intent", "period", "status", "subject"}
    ),
    "Condition": frozenset(
        {
            "abatementDateTime",
            "category",
            "clinicalStatus",
            "code",
            "encounter",
            "onsetDateTime",
            "recordedDate",
            "subject",
            "verificationStatus",
        }
    ),
    "DiagnosticReport": frozenset(
        {"category", "code", "effectiveDateTime", "encounter", "issued", "result", "subject"}
    ),
    "DocumentReference": frozenset(
        {"author", "category", "content", "date", "identifier", "status", "subject", "type"}
    ),
    "Encounter": frozenset(
        {"class", "identifier", "participant", "period", "reasonCode", "status", "subject", "type"}
    ),
    "Immunization": frozenset(
        {"encounter", "location", "occurrenceDateTime", "patient", "status", "vaccineCode"}
    ),
    "MedicationAdministration": frozenset(
        {
            "dosage",
            "effectiveDateTime",
            "medicationCodeableConcept",
            "reasonCode",
            "status",
            "subject",
        }
    ),
    "MedicationRequest": frozenset(
        {
            "authoredOn",
            "dosageInstruction",
            "encounter",
            "medicationCodeableConcept",
            "reasonCode",
            "requester",
            "status",
            "subject",
        }
    ),
    "Observation": frozenset(
        {
            "category",
            "code",
            "effectiveDateTime",
            "encounter",
            "issued",
            "status",
            "subject",
            "valueCodeableConcept",
            "valueQuantity",
            "valueString",
        }
    ),
    "Organization": frozenset({"active", "address", "identifier", "name", "telecom", "type"}),
    "Patient": frozenset(
        {
            "address",
            "birthDate",
            "deceasedDateTime",
            "gender",
            "identifier",
            "maritalStatus",
            "name",
            "telecom",
        }
    ),
    "Practitioner": frozenset({"active", "address", "gender", "identifier", "name", "telecom"}),
    "Procedure": frozenset(
        {"code", "encounter", "location", "performedPeriod", "reasonCode", "status", "subject"}
    ),
}


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resourceType: str
    instance: str
    keyword: str
    value: str

    @field_validator("resourceType", "instance", "keyword", "value")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @field_validator("instance")
    @classmethod
    def safe_instance(cls, value: str) -> str:
        if not _INSTANCE_SLUG.fullmatch(value):
            raise ValueError("instance must be a bounded lowercase slug")
        return value


def parse_entities(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw = payload.get("entities")
    if not isinstance(raw, list) or len(raw) > MAX_EXTRACTED_ENTITIES:
        raise ExtractionSchemaError("extraction must contain a bounded entities array")
    entities: list[dict[str, str]] = []
    try:
        parsed = [ExtractedEntity.model_validate(item) for item in raw]
    except (TypeError, ValueError):
        raise ExtractionSchemaError("an extracted entity violates the strict schema") from None
    for entity in parsed:
        allowed = RESOURCE_CATALOG.get(entity.resourceType)
        if allowed is None or entity.keyword not in allowed:
            raise ExtractionSchemaError("an extracted resource type or key is outside the catalog")
        entities.append(entity.model_dump())
    return entities


def resource_catalog_text() -> str:
    return "\n".join(
        f"{resource_type}: {', '.join(sorted(keys))}"
        for resource_type, keys in sorted(RESOURCE_CATALOG.items())
    )


__all__ = [
    "MAX_EXTRACTED_ENTITIES",
    "RESOURCE_CATALOG",
    "ExtractedEntity",
    "parse_entities",
    "resource_catalog_text",
]
