from __future__ import annotations

from typing import Any

from fhiratwill import (
    GENERIC_FHIR_TARGET,
    PlanStepStatus,
    PreflightCheck,
    PreflightReport,
    PreflightStatus,
    SubjectContext,
    compile_write_plan,
)


def test_plan_is_idempotent_and_excludes_generated_identity() -> None:
    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "fullUrl": "urn:uuid:patient",
                "resource": {"resourceType": "Patient", "gender": "female"},
            },
            {
                "fullUrl": "urn:uuid:observation",
                "resource": {
                    "resourceType": "Observation",
                    "subject": {"reference": "urn:uuid:patient"},
                },
            },
        ],
    }
    context = SubjectContext(patient_ref="Patient/123")
    first = compile_write_plan(
        bundle=bundle,
        context=context,
        conversion_id="conversion-1",
        tenant_id="tenant-1",
        descriptor=GENERIC_FHIR_TARGET,
    )
    second = compile_write_plan(
        bundle=bundle,
        context=context,
        conversion_id="conversion-1",
        tenant_id="tenant-1",
        descriptor=GENERIC_FHIR_TARGET,
    )
    assert [step.idempotency_key for step in first.steps] == [
        step.idempotency_key for step in second.steps
    ]
    assert first.steps[0].status is PlanStepStatus.EXCLUDED
    assert first.steps[1].resource["subject"]["reference"] == "Patient/123"
    assert first.transaction is not None
    assert len(first.transaction["entry"]) == 1


def test_failed_identity_preflight_blocks_every_writable_step() -> None:
    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": {"resourceType": "Observation"}}],
    }
    preflight = PreflightReport(
        status=PreflightStatus.FAILED,
        checks=[
            PreflightCheck(
                check="gender",
                status=PreflightStatus.FAILED,
                detail="patient gender mismatch",
            )
        ],
    )
    plan = compile_write_plan(
        bundle=bundle,
        context=SubjectContext(patient_ref="Patient/123"),
        conversion_id="conversion-1",
        tenant_id="tenant-1",
        descriptor=GENERIC_FHIR_TARGET,
        preflight=preflight,
    )
    assert plan.ready is False
    assert plan.transaction is None
    assert plan.steps[0].status is PlanStepStatus.BLOCKED
