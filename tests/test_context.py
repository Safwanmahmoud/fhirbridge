from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from fhiratwill import PreflightStatus, SubjectContext, rebind_bundle, run_preflight


class DirectReader:
    def __init__(self, resources: dict[str, dict[str, Any]]) -> None:
        self.resources = resources
        self.reads: list[str] = []

    async def read(self, reference: str) -> dict[str, Any]:
        self.reads.append(reference)
        return self.resources[reference]


def source_bundle() -> dict[str, Any]:
    return {
        "entry": [
            {
                "fullUrl": "urn:uuid:patient",
                "resource": {"resourceType": "Patient", "gender": "female"},
            },
            {
                "fullUrl": "urn:uuid:encounter",
                "resource": {"resourceType": "Encounter"},
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "subject": {"reference": "urn:uuid:patient"},
                    "encounter": {"reference": "urn:uuid:encounter"},
                }
            },
        ]
    }


def test_rebind_excludes_generated_identity_and_rewrites_references() -> None:
    rebound, notes = rebind_bundle(
        source_bundle(),
        SubjectContext(patient_ref="Patient/123", encounter_ref="Encounter/456"),
    )
    observation = rebound["entry"][2]["resource"]
    assert rebound["entry"][0]["_writeExcluded"] is True
    assert rebound["entry"][1]["_writeExcluded"] is True
    assert observation["subject"]["reference"] == "Patient/123"
    assert observation["encounter"]["reference"] == "Encounter/456"
    assert len(notes) == 2


@pytest.mark.asyncio
async def test_wrong_patient_guard_only_reads_supplied_identity() -> None:
    reader = DirectReader(
        {"Patient/123": {"resourceType": "Patient", "gender": "male", "birthDate": "2000-01-01"}}
    )
    report = await run_preflight(
        bundle={"entry": [{"resource": {"resourceType": "Patient", "gender": "female"}}]},
        context=SubjectContext(patient_ref="Patient/123"),
        reader=reader,
        today=date(2026, 9, 6),
    )
    assert report.status is PreflightStatus.FAILED
    assert reader.reads == ["Patient/123"]
    assert all(
        "female" not in check.detail and "male" not in check.detail for check in report.checks
    )
