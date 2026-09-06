"""L2 profile and L4 invariant normalization for validator adapters."""

from __future__ import annotations

import re
import time
from typing import Any

from fhiratwill.validation.adapters import ValidatorClient, ValidatorIssue
from fhiratwill.validation.models import (
    IssueSeverity,
    LayerResult,
    LayerStatus,
    ValidationIssue,
    ValidationLayer,
)
from fhiratwill.validation.rules import load_rule_yaml

_SEVERITY = {
    "fatal": IssueSeverity.FATAL,
    "error": IssueSeverity.ERROR,
    "warning": IssueSeverity.WARNING,
    "information": IssueSeverity.INFORMATION,
    "informational": IssueSeverity.INFORMATION,
    "success": IssueSeverity.INFORMATION,
}


async def validate_profile(
    payload: dict[str, Any], *, client: ValidatorClient, profiles: tuple[str, ...]
) -> LayerResult:
    started = time.perf_counter()
    outcome = await client.validate_resource(payload, profiles=profiles)
    issues = [_translate_profile(issue) for issue in outcome.issues[:500]]
    return _result(ValidationLayer.PROFILE, issues, started)


async def validate_invariants(
    payload: dict[str, Any],
    *,
    client: ValidatorClient,
    resource_type: str,
    expected_version: int,
) -> LayerResult:
    started = time.perf_counter()
    pack = load_rule_yaml("invariants.yaml", expected_version=expected_version)
    targets = [(resource_type, payload, resource_type)]
    if resource_type == "Bundle":
        for index, entry in enumerate(payload.get("entry", []) or []):
            resource = entry.get("resource") if isinstance(entry, dict) else None
            nested = resource.get("resourceType") if isinstance(resource, dict) else None
            if isinstance(resource, dict) and isinstance(nested, str):
                targets.append((nested, resource, f"Bundle.entry[{index}].resource"))
    issues: list[ValidationIssue] = []
    notes: list[str] = []
    evaluated = 0
    limit = int(pack.get("max_evaluations", 200))
    for target_type, target, location in targets:
        for rule in pack.get("invariants", []):
            if evaluated >= limit:
                notes.append("Invariant evaluation budget exhausted; remaining rules did not pass.")
                break
            applies = rule.get("applies_to", ["*"])
            if "*" not in applies and target_type not in applies:
                continue
            evaluated += 1
            try:
                outcome = await client.evaluate_fhirpath(target, str(rule["expression"]))
            except ValueError:
                if not rule.get("tolerate_evaluation_failure", False):
                    issues.append(
                        _invariant_issue(rule, IssueSeverity.WARNING, location, "was inconclusive")
                    )
                continue
            if outcome.is_true:
                continue
            if not outcome.values:
                if not rule.get("tolerate_evaluation_failure", False):
                    issues.append(
                        _invariant_issue(rule, IssueSeverity.WARNING, location, "was inconclusive")
                    )
            else:
                issues.append(
                    _invariant_issue(
                        rule, IssueSeverity(str(rule.get("severity", "error"))), location, "failed"
                    )
                )
    notes.insert(0, f"Evaluated {evaluated} invariant(s) across {len(targets)} resource(s).")
    result = _result(ValidationLayer.INVARIANTS, issues, started)
    result.notes = notes
    return result


def _translate_profile(issue: ValidatorIssue) -> ValidationIssue:
    return ValidationIssue(
        layer=ValidationLayer.PROFILE,
        severity=_SEVERITY.get(issue.severity.lower(), IssueSeverity.ERROR),
        code=issue.code if re.fullmatch(r"[a-z0-9-]{1,64}", issue.code) else "processing",
        message="The validator reported a profile conformance issue.",
        expression=(
            issue.expression
            if issue.expression is not None
            and re.fullmatch(r"[A-Za-z$][A-Za-z0-9_$.\[\]-]{0,255}", issue.expression)
            else None
        ),
        line=issue.line,
        column=issue.column,
    )


def _invariant_issue(
    rule: dict[str, Any], severity: IssueSeverity, location: str, outcome: str
) -> ValidationIssue:
    return ValidationIssue(
        layer=ValidationLayer.INVARIANTS,
        severity=severity,
        code="invariant" if outcome == "failed" else "incomplete",
        message=f"{rule['id']} {outcome}: {rule.get('human', '')}",
        expression=location,
        rule_id=str(rule["id"]),
    )


def _result(layer: ValidationLayer, issues: list[ValidationIssue], started: float) -> LayerResult:
    return LayerResult(
        layer=layer,
        layer_number=layer.number,
        status=LayerStatus.FAILED
        if any(issue.severity.is_blocking for issue in issues)
        else LayerStatus.PASSED,
        blocking=True,
        issues=issues,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


__all__ = ["validate_invariants", "validate_profile"]
