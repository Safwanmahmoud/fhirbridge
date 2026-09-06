from __future__ import annotations

from fhiratwill import AssemblyAction, assemble_bundle


def entity(kind: str, instance: str, keyword: str, value: str) -> dict[str, str]:
    return {"resourceType": kind, "instance": instance, "keyword": keyword, "value": value}


def test_assembly_is_deterministic_and_keeps_text_uncoded() -> None:
    entities = [
        entity("Patient", "patient", "gender", "female"),
        entity("Observation", "pulse", "code", "heart rate"),
        entity("Observation", "pulse", "valueQuantity", "72/min"),
    ]
    first = assemble_bundle(entities, seed="fixed")
    second = assemble_bundle(list(reversed(entities)), seed="fixed")
    assert first.bundle == second.bundle
    observation = first.bundle["entry"][1]["resource"]
    assert observation["code"] == {"text": "heart rate"}
    assert observation["valueQuantity"] == {"value": 72, "unit": "/min"}


def test_unsafe_coercion_is_refused_with_phi_free_note() -> None:
    secret = "SECRET-CLINICAL-VALUE"
    result = assemble_bundle(
        [entity("Patient", "patient", "birthDate", secret)],
        seed="fixed",
    )
    patient = result.bundle["entry"][0]["resource"]
    assert "birthDate" not in patient
    assert result.notes[0].action is AssemblyAction.DROPPED
    assert secret not in result.notes[0].detail
