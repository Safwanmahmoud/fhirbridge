"""L3 independent terminology verification through an injected adapter."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fhiratwill.errors import UnknownValueSetError
from fhiratwill.terminology import TerminologyClient
from fhiratwill.validation.models import (
    IssueSeverity,
    LayerResult,
    LayerStatus,
    ValidationIssue,
    ValidationLayer,
)
from fhiratwill.validation.rules import load_rule_yaml


class BindingStrength(StrEnum):
    REQUIRED = "required"
    EXTENSIBLE = "extensible"
    PREFERRED = "preferred"
    EXAMPLE = "example"

    @property
    def is_blocking(self) -> bool:
        return self is self.REQUIRED


@dataclass(frozen=True, slots=True)
class Binding:
    path: str
    value_set: str
    strength: BindingStrength
    kind: str


async def validate_terminology(
    payload: dict[str, Any],
    *,
    client: TerminologyClient,
    expected_version: int = 1,
    max_checks: int = 250,
) -> LayerResult:
    started = time.perf_counter()
    raw = load_rule_yaml("bindings.yaml", expected_version=expected_version)
    bindings = {
        str(item["path"]): Binding(
            str(item["path"]),
            str(item["value_set"]),
            BindingStrength(str(item["strength"])),
            str(item["kind"]),
        )
        for item in raw.get("bindings", [])
    }
    issues: list[ValidationIssue] = []
    notes: list[str] = []
    checks = 0
    for value, path, location, is_quantity in _walk(payload):
        if checks >= max_checks:
            notes.append(f"Stopped after {max_checks} terminology checks; coverage is incomplete.")
            break
        binding = bindings.get(path)
        if is_quantity:
            system, code = value.get("system"), value.get("code")
            if system in set(raw.get("unit_systems", [])) and isinstance(code, str):
                checks += 1
                outcome = await client.validate_code(system=system, code=code)
                if not outcome.result:
                    issues.append(_issue(IssueSeverity.WARNING, "code-invalid", location))
            continue
        if "coding" in value and isinstance(value.get("coding"), list):
            for index, coding in enumerate(value["coding"]):
                if checks >= max_checks or not isinstance(coding, dict):
                    break
                code, system = coding.get("code"), coding.get("system")
                if not isinstance(code, str):
                    continue
                if not isinstance(system, str):
                    issues.append(
                        _issue(IssueSeverity.ERROR, "code-invalid", f"{location}.coding[{index}]")
                    )
                    continue
                checks += 1
                outcome = await client.validate_code(
                    system=system,
                    code=code,
                    display=coding.get("display"),
                    version=coding.get("version"),
                )
                if not outcome.result:
                    issues.append(
                        _issue(IssueSeverity.ERROR, "code-invalid", f"{location}.coding[{index}]")
                    )
                if binding is not None and binding.strength in {
                    BindingStrength.REQUIRED,
                    BindingStrength.EXTENSIBLE,
                }:
                    checks += 1
                    await _check_binding(
                        client, binding, system, code, coding, f"{location}.coding[{index}]", issues
                    )
        elif binding is not None:
            primitive = value.get("_primitive")
            if isinstance(primitive, str):
                checks += 1
                await _check_binding(client, binding, None, primitive, {}, location, issues)
    notes.insert(0, f"Made {checks} terminology check(s) using {len(bindings)} curated bindings.")
    return LayerResult(
        layer=ValidationLayer.TERMINOLOGY,
        layer_number=3,
        status=LayerStatus.FAILED
        if any(issue.severity.is_blocking for issue in issues)
        else LayerStatus.PASSED,
        blocking=True,
        issues=issues,
        notes=notes,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


async def _check_binding(
    client: TerminologyClient,
    binding: Binding,
    system: str | None,
    code: str,
    coding: dict[str, Any],
    location: str,
    issues: list[ValidationIssue],
) -> None:
    try:
        outcome = await client.validate_code(
            system=system,
            code=code,
            display=coding.get("display"),
            version=coding.get("version"),
            value_set=binding.value_set,
        )
    except UnknownValueSetError:
        severity = IssueSeverity.ERROR if binding.strength.is_blocking else IssueSeverity.WARNING
        issues.append(_issue(severity, "not-found", location))
        return
    if not outcome.result:
        severity = IssueSeverity.ERROR if binding.strength.is_blocking else IssueSeverity.WARNING
        issues.append(_issue(severity, "code-invalid", location))


def _walk(
    resource: dict[str, Any],
) -> list[tuple[dict[str, Any], str, str, bool]]:
    found: list[tuple[dict[str, Any], str, str, bool]] = []

    def visit(value: Any, definition: str, location: str) -> None:
        if isinstance(value, dict):
            if "coding" in value:
                found.append((value, definition, location, False))
            if "value" in value and ("unit" in value or "code" in value):
                found.append((value, definition, location, True))
            for key, child in value.items():
                if key == "resourceType":
                    continue
                next_definition = f"{definition}.{key}"
                next_location = f"{location}.{key}"
                if isinstance(child, dict) and isinstance(child.get("resourceType"), str):
                    next_definition = str(child["resourceType"])
                visit(child, next_definition, next_location)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, definition, f"{location}[{index}]")
        elif isinstance(value, str):
            found.append(({"_primitive": value}, definition, location, False))

    root = str(resource.get("resourceType", "Unknown"))
    visit(resource, root, root)
    return found


def _issue(severity: IssueSeverity, code: str, _expression: str) -> ValidationIssue:
    return ValidationIssue(
        layer=ValidationLayer.TERMINOLOGY,
        severity=severity,
        code=code,
        message="The terminology adapter could not confirm this code.",
    )


__all__ = ["Binding", "BindingStrength", "validate_terminology"]
