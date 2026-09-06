"""Subject-context rebinding and read-only wrong-patient preflight."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from fhiratwill.errors import FhiratwillError, TargetUnavailableError


@dataclass(frozen=True, slots=True)
class SubjectContext:
    """Caller-supplied destination references; identity is never inferred or searched."""

    patient_ref: str
    encounter_ref: str | None = None
    author_ref: str | None = None


class PlanNote(BaseModel):
    """PHI-free planning evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    entry_index: int = Field(ge=0)
    resource_type: str
    element: str
    action: str
    detail: str


class PreflightStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PreflightCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    check: str
    status: PreflightStatus
    detail: str


class PreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: PreflightStatus
    checks: list[PreflightCheck] = Field(default_factory=list)


class ResourceReader(Protocol):
    """Minimal adapter: direct read only, deliberately no identity-search operation."""

    async def read(self, reference: str) -> dict[str, Any]: ...


def rebind_bundle(
    bundle: dict[str, Any], context: SubjectContext
) -> tuple[dict[str, Any], tuple[PlanNote, ...]]:
    """Replace local identity references and mark generated Patient/Encounter excluded."""
    rebound = copy.deepcopy(bundle)
    entries = rebound.get("entry")
    if not isinstance(entries, list):
        return rebound, ()
    replacements: dict[str, str] = {}
    notes: list[PlanNote] = []
    for index, entry in enumerate(entries):
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            continue
        resource_type = str(resource.get("resourceType", ""))
        target = {
            "Patient": context.patient_ref,
            "Encounter": context.encounter_ref,
            "Practitioner": context.author_ref,
        }.get(resource_type)
        full_url = entry.get("fullUrl")
        if isinstance(full_url, str) and target:
            replacements[full_url] = target
        if resource_type in {"Patient", "Encounter"}:
            entry["_writeExcluded"] = True
            notes.append(
                PlanNote(
                    entry_index=index,
                    resource_type=resource_type,
                    element="resource",
                    action="excluded",
                    detail=(
                        "destination identity is caller supplied; generated identity is excluded"
                    ),
                )
            )

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            reference = value.get("reference")
            if isinstance(reference, str) and reference in replacements:
                value["reference"] = replacements[reference]
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(rebound)
    return rebound, tuple(notes)


async def run_preflight(
    *,
    bundle: dict[str, Any],
    context: SubjectContext,
    reader: ResourceReader,
    today: date | None = None,
) -> PreflightReport:
    """Compare narrative evidence only with direct reads of supplied references."""
    try:
        patient = await reader.read(context.patient_ref)
        encounter = await reader.read(context.encounter_ref) if context.encounter_ref else None
    except FhiratwillError:
        raise
    except Exception as exc:
        raise TargetUnavailableError("destination context could not be read") from exc
    checks: list[PreflightCheck] = []
    _check_gender(checks, _first_resource(bundle, "Patient"), patient)
    _check_age(checks, bundle, patient, today or datetime.now(UTC).date())
    _check_encounter(checks, bundle, encounter)
    if any(check.status is PreflightStatus.FAILED for check in checks):
        status = PreflightStatus.FAILED
    elif checks and all(check.status is PreflightStatus.SKIPPED for check in checks):
        status = PreflightStatus.SKIPPED
    else:
        status = PreflightStatus.PASSED
    return PreflightReport(status=status, checks=checks)


def _first_resource(bundle: dict[str, Any], kind: str) -> dict[str, Any] | None:
    entries = bundle.get("entry", [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if isinstance(resource, dict) and resource.get("resourceType") == kind:
            return resource
    return None


def _check_gender(
    checks: list[PreflightCheck],
    narrative: dict[str, Any] | None,
    patient: dict[str, Any],
) -> None:
    stated = narrative.get("gender") if narrative else None
    actual = patient.get("gender")
    if not isinstance(stated, str):
        checks.append(
            PreflightCheck(check="gender", status=PreflightStatus.SKIPPED, detail="not stated")
        )
    elif not isinstance(actual, str) or stated.casefold() != actual.casefold():
        checks.append(
            PreflightCheck(
                check="gender",
                status=PreflightStatus.FAILED,
                detail="patient gender mismatch",
            )
        )
    else:
        checks.append(
            PreflightCheck(check="gender", status=PreflightStatus.PASSED, detail="matched")
        )


def _check_age(
    checks: list[PreflightCheck],
    bundle: dict[str, Any],
    patient: dict[str, Any],
    today: date,
) -> None:
    age = _narrative_age(bundle)
    if age is None:
        checks.append(
            PreflightCheck(check="age", status=PreflightStatus.SKIPPED, detail="not stated")
        )
        return
    try:
        born = date.fromisoformat(str(patient.get("birthDate")))
    except ValueError:
        checks.append(
            PreflightCheck(
                check="age",
                status=PreflightStatus.FAILED,
                detail="patient birthDate unavailable",
            )
        )
        return
    actual = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    passed = abs(actual - age) <= 1
    checks.append(
        PreflightCheck(
            check="age",
            status=PreflightStatus.PASSED if passed else PreflightStatus.FAILED,
            detail="matched within tolerance" if passed else "birthDate outside tolerance",
        )
    )


def _narrative_age(bundle: dict[str, Any]) -> int | None:
    entries = bundle.get("entry", [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict) or resource.get("resourceType") != "Observation":
            continue
        code = resource.get("code")
        value = resource.get("valueQuantity")
        text = code.get("text") if isinstance(code, dict) else None
        raw = value.get("value") if isinstance(value, dict) else None
        if (
            isinstance(text, str)
            and text.casefold().strip() == "age"
            and isinstance(raw, (int, float))
        ):
            return int(raw)
    return None


def _check_encounter(
    checks: list[PreflightCheck],
    bundle: dict[str, Any],
    encounter: dict[str, Any] | None,
) -> None:
    narrative = _first_resource(bundle, "Encounter")
    period = narrative.get("period") if narrative else None
    if not isinstance(period, dict):
        checks.append(
            PreflightCheck(
                check="encounter_period",
                status=PreflightStatus.SKIPPED,
                detail="not stated",
            )
        )
        return
    target_period = encounter.get("period") if encounter else None
    if not isinstance(target_period, dict):
        checks.append(
            PreflightCheck(
                check="encounter_period",
                status=PreflightStatus.FAILED,
                detail="target encounter period unavailable",
            )
        )
        return
    passed = period.get("start") == target_period.get("start")
    checks.append(
        PreflightCheck(
            check="encounter_period",
            status=PreflightStatus.PASSED if passed else PreflightStatus.FAILED,
            detail="matched" if passed else "encounter period mismatch",
        )
    )


__all__ = [
    "PlanNote",
    "PreflightCheck",
    "PreflightReport",
    "PreflightStatus",
    "ResourceReader",
    "SubjectContext",
    "rebind_bundle",
    "run_preflight",
]
