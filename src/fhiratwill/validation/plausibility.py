"""L5 deterministic checks for impossible values (never diagnosis)."""

from __future__ import annotations

import time
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fhiratwill.validation.models import (
    IssueSeverity,
    LayerResult,
    LayerStatus,
    ValidationIssue,
    ValidationLayer,
)
from fhiratwill.validation.rules import load_rule_yaml


def validate_plausibility(
    payload: object,
    *,
    resource_type: str | None,
    expected_version: int = 1,
    severity_overrides: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> LayerResult:
    started = time.perf_counter()
    pack = load_rule_yaml("plausibility.yaml", expected_version=expected_version)
    targets = _targets(payload, resource_type)
    patients = _patients(payload, resource_type)
    overrides = severity_overrides or {}
    reference = now or datetime.now(UTC)
    tolerance = int((pack.get("defaults") or {}).get("future_date_tolerance_days", 1))
    issues: list[ValidationIssue] = []
    rules = [rule for rule in pack.get("rules", []) if rule.get("enabled", True)]
    for resource, location in targets:
        kind = str(resource.get("resourceType", ""))
        for rule in rules:
            applies = rule.get("applies_to", ["*"])
            if "*" not in applies and kind not in applies:
                continue
            findings = _apply(rule, resource, location, reference, tolerance, patients)
            severity = IssueSeverity(str(overrides.get(str(rule["id"]), rule["severity"])))
            issues.extend(
                ValidationIssue(
                    layer=ValidationLayer.PLAUSIBILITY,
                    severity=severity,
                    code="business-rule",
                    message=message,
                    expression=expression,
                    rule_id=str(rule["id"]),
                )
                for message, expression in findings
            )
    return LayerResult(
        layer=ValidationLayer.PLAUSIBILITY,
        layer_number=5,
        status=LayerStatus.FAILED
        if any(issue.severity.is_blocking for issue in issues)
        else LayerStatus.PASSED,
        blocking=True,
        issues=issues,
        notes=[
            f"Applied {len(rules)} enabled rule(s) to {len(targets)} resource(s).",
            "L5 flags impossible values only; it does not diagnose or interpret treatment.",
        ],
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def _apply(
    rule: dict[str, Any],
    resource: dict[str, Any],
    location: str,
    now: datetime,
    tolerance: int,
    patients: dict[str, dict[str, Any]],
) -> list[tuple[str, str]]:
    kind = rule["kind"]
    if kind in {"quantity_range", "non_negative_quantity"}:
        return _quantities(rule, resource, location)
    if kind == "future_date":
        findings = []
        for path in rule.get("paths", []):
            if not str(path).startswith(f"{resource.get('resourceType')}."):
                continue
            element = str(path).split(".", 1)[1]
            moment = _parse_datetime(resource.get(element))
            if moment is not None and moment > now + timedelta(days=tolerance):
                findings.append((str(rule["message"]), f"{location}.{element}"))
        return findings
    if kind == "date_order":
        findings = []
        for pair in rule.get("pairs", []):
            left = str(pair["earlier"]).split(".", 1)[1]
            right = str(pair["later"]).split(".", 1)[1]
            earlier = _parse_datetime(resource.get(left))
            later = _parse_datetime(resource.get(right))
            if earlier is not None and later is not None and earlier > later:
                findings.append((str(rule["message"]), f"{location}.{right}"))
        return findings
    if kind == "birth_date_order":
        subject = resource.get("subject") or resource.get("patient")
        reference = subject.get("reference") if isinstance(subject, dict) else None
        patient = patients.get(str(reference)) if reference else None
        unique = {id(item): item for item in patients.values()}
        if patient is None and len(unique) == 1:
            patient = next(iter(unique.values()))
        birth = _parse_datetime(patient.get("birthDate")) if patient else None
        if birth is None:
            return []
        findings = []
        for path in rule.get("paths", []):
            if not str(path).startswith(f"{resource.get('resourceType')}."):
                continue
            element = str(path).split(".", 1)[1]
            moment = _parse_datetime(resource.get(element))
            if moment is not None and moment < birth:
                findings.append((str(rule["message"]), f"{location}.{element}"))
        return findings
    if kind == "dose_magnitude":
        findings = []
        for i, dosage in enumerate(resource.get("dosage", []) or []):
            for j, dose_rate in enumerate((dosage or {}).get("doseAndRate", []) or []):
                quantity = (dose_rate or {}).get("doseQuantity") or {}
                value = _float(quantity.get("value"))
                unit = quantity.get("code") or quantity.get("unit")
                limit = (rule.get("limits") or {}).get(unit)
                if value is not None and limit is not None and value > float(limit):
                    findings.append(
                        (
                            str(rule["message"]),
                            f"{location}.dosage[{i}].doseAndRate[{j}].doseQuantity.value",
                        )
                    )
        return findings
    return []


def _quantities(
    rule: dict[str, Any], resource: dict[str, Any], location: str
) -> list[tuple[str, str]]:
    holders: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    if isinstance(resource.get("valueQuantity"), dict):
        holders.append((resource, resource["valueQuantity"], f"{location}.valueQuantity"))
    for index, component in enumerate(resource.get("component", []) or []):
        if isinstance(component, dict) and isinstance(component.get("valueQuantity"), dict):
            holders.append(
                (
                    component,
                    component["valueQuantity"],
                    f"{location}.component[{index}].valueQuantity",
                )
            )
    findings = []
    for holder, quantity, path in holders:
        value = _float(quantity.get("value"))
        if value is None:
            continue
        if rule["kind"] == "non_negative_quantity" and value < 0:
            findings.append((str(rule["message"]), f"{path}.value"))
            continue
        codings = (holder.get("code") or {}).get("coding", []) or []
        codes = {
            f"{coding.get('system')}|{coding.get('code')}"
            for coding in codings
            if isinstance(coding, dict)
        }
        if not codes.intersection(rule.get("codes", [])):
            continue
        unit = quantity.get("code") or quantity.get("unit")
        if rule.get("expected_unit") and unit and unit != rule["expected_unit"]:
            findings.append(
                ("Unit does not match the rule; range was not applied.", f"{path}.code")
            )
        elif value < float(rule["min"]) or value > float(rule["max"]):
            findings.append((str(rule["message"]), f"{path}.value"))
    return findings


def _targets(payload: object, resource_type: str | None) -> list[tuple[dict[str, Any], str]]:
    if not isinstance(payload, dict) or resource_type is None:
        return []
    result = [(payload, resource_type)]
    if resource_type == "Bundle":
        for index, entry in enumerate(payload.get("entry", []) or []):
            resource = entry.get("resource") if isinstance(entry, dict) else None
            if isinstance(resource, dict):
                result.append((resource, f"Bundle.entry[{index}].resource"))
    return result


def _patients(payload: object, resource_type: str | None) -> dict[str, dict[str, Any]]:
    patients: dict[str, dict[str, Any]] = {}
    for resource, _location in _targets(payload, resource_type):
        if resource.get("resourceType") != "Patient":
            continue
        identifier = resource.get("id")
        if isinstance(identifier, str):
            patients[identifier] = resource
            patients[f"Patient/{identifier}"] = resource
    return patients


def _float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value) if isinstance(value, int | float | str) else None
    except ValueError:
        return None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 4:
            return datetime(int(value), 1, 1, tzinfo=UTC)
        if len(value) == 7:
            year, month = value.split("-")
            return datetime(int(year), int(month), 1, tzinfo=UTC)
        if len(value) == 10:
            parsed = date.fromisoformat(value)
            return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)
        parsed_dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed_dt if parsed_dt.tzinfo else parsed_dt.replace(tzinfo=UTC)
    except ValueError:
        return None


__all__ = ["validate_plausibility"]
