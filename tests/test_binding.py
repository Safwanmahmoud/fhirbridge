from __future__ import annotations

from typing import Any

import pytest

from fhiratwill import BindingAction, TerminologyUnavailableError, bind_bundle
from tests.fakes import FakeTerminologyClient


def bundle() -> dict[str, Any]:
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Observation",
                    "code": {"text": "Heart rate"},
                    "valueQuantity": {"value": 72, "unit": "beats/minute"},
                }
            }
        ],
    }


@pytest.mark.asyncio
async def test_binding_verifies_codes_and_retains_text() -> None:
    result = await bind_bundle(bundle(), client=FakeTerminologyClient())
    observation = result.bundle["entry"][0]["resource"]
    assert observation["code"]["text"] == "Heart rate"
    assert observation["code"]["coding"][0]["code"] == "8867-4"
    assert observation["valueQuantity"]["code"] == "/min"


@pytest.mark.asyncio
async def test_invalid_candidate_is_refused() -> None:
    result = await bind_bundle(bundle(), client=FakeTerminologyClient(membership={"8867-4": False}))
    observation = result.bundle["entry"][0]["resource"]
    assert "coding" not in observation["code"]
    assert any(note.action is BindingAction.UNBOUND for note in result.notes)


@pytest.mark.asyncio
async def test_terminology_outage_propagates() -> None:
    with pytest.raises(TerminologyUnavailableError):
        await bind_bundle(bundle(), client=FakeTerminologyClient(unavailable=True))


@pytest.mark.asyncio
async def test_unknown_unit_reports_zero_candidates() -> None:
    payload = bundle()
    payload["entry"][0]["resource"]["valueQuantity"]["unit"] = "unknown-unit"
    result = await bind_bundle(payload, client=FakeTerminologyClient())
    unit_note = next(note for note in result.notes if note.element == "valueQuantity")
    assert unit_note.action is BindingAction.UNBOUND
    assert unit_note.candidate_count == 0
