"""Compile a rebound collection Bundle into a deterministic write plan."""

from __future__ import annotations

import copy
import hashlib
from enum import StrEnum
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from fhiratwill.context import (
    PlanNote,
    PreflightReport,
    PreflightStatus,
    SubjectContext,
    rebind_bundle,
)
from fhiratwill.targets import TargetDescriptor

_IDENTIFIER_SYSTEM = "https://fhirbridge.org/identifier/write"


class PlanStepStatus(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    EXCLUDED = "excluded"


class WriteStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    step_index: int = Field(ge=0)
    entry_index: int = Field(ge=0)
    target_api: str
    method: str
    url: str
    resource: dict[str, Any]
    depends_on: tuple[int, ...] = ()
    idempotency_key: str
    status: PlanStepStatus


class WritePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    conversion_id: str
    target_id: str
    descriptor_version: str
    ready: bool
    transaction: dict[str, Any] | None = None
    steps: list[WriteStep] = Field(default_factory=list)
    notes: list[PlanNote] = Field(default_factory=list)
    preflight: PreflightReport | None = None


def compile_write_plan(
    *,
    bundle: dict[str, Any],
    context: SubjectContext,
    conversion_id: str,
    tenant_id: str,
    descriptor: TargetDescriptor,
    preflight: PreflightReport | None = None,
) -> WritePlan:
    """Create an idempotent plan only; this function performs no I/O."""
    rebound, rebind_notes = rebind_bundle(bundle, context)
    notes = list(rebind_notes)
    raw_entries = rebound.get("entry", [])
    entries = raw_entries if isinstance(raw_entries, list) else []
    preflight_failed = preflight is not None and preflight.status is PreflightStatus.FAILED
    entry_to_step: dict[int, int] = {}
    for entry_index, entry in enumerate(entries):
        if isinstance(entry, dict) and isinstance(entry.get("resource"), dict):
            entry_to_step[entry_index] = len(entry_to_step)
    full_url_to_step = {
        str(entry["fullUrl"]): entry_to_step[index]
        for index, entry in enumerate(entries)
        if (
            index in entry_to_step
            and isinstance(entry, dict)
            and not entry.get("_writeExcluded")
            and isinstance(entry.get("fullUrl"), str)
        )
    }
    steps: list[WriteStep] = []
    transaction_entries: list[dict[str, Any]] = []
    for entry_index, entry in enumerate(entries):
        resource_value = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource_value, dict):
            continue
        resource = copy.deepcopy(resource_value)
        resource_type = str(resource.get("resourceType", ""))
        excluded = bool(entry.get("_writeExcluded"))
        accepted = descriptor.accepts(resource_type)
        status = (
            PlanStepStatus.EXCLUDED
            if excluded
            else PlanStepStatus.BLOCKED
            if preflight_failed
            else PlanStepStatus.READY
            if accepted
            else PlanStepStatus.BLOCKED
        )
        if preflight_failed and not excluded:
            notes.append(
                PlanNote(
                    entry_index=entry_index,
                    resource_type=resource_type,
                    element="context",
                    action="blocked",
                    detail="destination identity preflight failed",
                )
            )
        if not accepted and not excluded:
            notes.append(
                PlanNote(
                    entry_index=entry_index,
                    resource_type=resource_type,
                    element="resourceType",
                    action="blocked",
                    detail="resource type is not accepted by the target descriptor",
                )
            )
        for element in descriptor.forbidden_elements.get(resource_type, frozenset()):
            if element in resource:
                resource.pop(element)
                notes.append(
                    PlanNote(
                        entry_index=entry_index,
                        resource_type=resource_type,
                        element=element,
                        action="stripped",
                        detail="element is forbidden by the target descriptor",
                    )
                )
        key = _idempotency_key(tenant_id, conversion_id, entry_index, descriptor.target_id)
        steps.append(
            WriteStep(
                step_index=len(steps),
                entry_index=entry_index,
                target_api=f"{resource_type}.create",
                method="POST",
                url=resource_type,
                resource=resource,
                depends_on=tuple(sorted(_referenced_steps(resource, full_url_to_step))),
                idempotency_key=key,
                status=status,
            )
        )
        if status is PlanStepStatus.READY:
            resource = copy.deepcopy(resource)
            identifier = {"system": _IDENTIFIER_SYSTEM, "value": key}
            existing = resource.get("identifier")
            if isinstance(existing, list):
                existing.append(identifier)
            elif existing is None:
                resource["identifier"] = [identifier]
            else:
                resource["identifier"] = [existing, identifier]
            transaction_entries.append(
                {
                    "fullUrl": entry.get("fullUrl"),
                    "resource": resource,
                    "request": {
                        "method": "POST",
                        "url": resource_type,
                        "ifNoneExist": (
                            f"identifier={quote(_IDENTIFIER_SYSTEM, safe='')}%7C"
                            f"{quote(key, safe='')}"
                        ),
                    },
                }
            )
    ready = not any(step.status is PlanStepStatus.BLOCKED for step in steps)
    transaction = (
        {"resourceType": "Bundle", "type": "transaction", "entry": transaction_entries}
        if descriptor.supports_transaction and ready
        else None
    )
    return WritePlan(
        conversion_id=conversion_id,
        target_id=descriptor.target_id,
        descriptor_version=descriptor.version,
        ready=ready,
        transaction=transaction,
        steps=steps,
        notes=notes,
        preflight=preflight,
    )


def _idempotency_key(tenant_id: str, conversion_id: str, index: int, target_id: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{conversion_id}:{index}:{target_id}".encode()).hexdigest()


def _referenced_steps(resource: Any, full_urls: dict[str, int]) -> set[int]:
    found: set[int] = set()
    if isinstance(resource, dict):
        reference = resource.get("reference")
        if isinstance(reference, str) and reference in full_urls:
            found.add(full_urls[reference])
        for value in resource.values():
            found.update(_referenced_steps(value, full_urls))
    elif isinstance(resource, list):
        for value in resource:
            found.update(_referenced_steps(value, full_urls))
    return found


__all__ = ["PlanStepStatus", "WritePlan", "WriteStep", "compile_write_plan"]
