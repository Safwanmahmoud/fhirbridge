from __future__ import annotations

import pytest

from fhiratwill.errors import TerminologyUnavailableError
from fhiratwill.validation import (
    LayerStatus,
    RoutingDecision,
    ValidationLayer,
    ValidatorIssue,
    ValidatorUnavailableError,
    validate,
)
from tests.validation_fakes import FakeTerminology, FakeValidator


def observation(value: float = 72) -> dict[str, object]:
    return {
        "resourceType": "Observation",
        "status": "preliminary",
        "code": {
            "coding": [{"system": "http://loinc.org", "code": "8867-4"}],
            "text": "Heart rate",
        },
        "valueQuantity": {
            "value": value,
            "unit": "beats/minute",
            "system": "http://unitsofmeasure.org",
            "code": "/min",
        },
    }


@pytest.mark.asyncio
async def test_local_mode_is_honest_about_all_eight_layers() -> None:
    report = await validate(observation())
    assert [layer.layer for layer in report.layers] == list(ValidationLayer)
    assert report.layer(ValidationLayer.STRUCTURAL).status is LayerStatus.PASSED  # type: ignore[union-attr]
    assert report.layer(ValidationLayer.PLAUSIBILITY).status is LayerStatus.PASSED  # type: ignore[union-attr]
    for layer in (
        ValidationLayer.PROFILE,
        ValidationLayer.TERMINOLOGY,
        ValidationLayer.INVARIANTS,
    ):
        result = report.layer(layer)
        assert result is not None
        assert result.status is LayerStatus.SKIPPED
        assert result.blocking
        assert "adapter" in (result.skipped_reason or "").lower()
    assert report.layer(ValidationLayer.FIDELITY).status is LayerStatus.NOT_APPLICABLE  # type: ignore[union-attr]
    assert report.layer(ValidationLayer.COVERAGE).status is LayerStatus.NOT_APPLICABLE  # type: ignore[union-attr]
    assert report.status is RoutingDecision.NEEDS_REVIEW
    assert not report.conformant


@pytest.mark.asyncio
async def test_structural_failure_rejects_but_l5_still_runs() -> None:
    report = await validate({"status": "final"})
    assert report.status is RoutingDecision.REJECT
    assert report.layer(ValidationLayer.STRUCTURAL).status is LayerStatus.FAILED  # type: ignore[union-attr]
    assert report.layer(ValidationLayer.PLAUSIBILITY).status is LayerStatus.PASSED  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_unknown_resource_type_is_not_echoed() -> None:
    unsafe = "Synthetic Patient Name"
    report = await validate({"resourceType": unsafe})

    assert report.resource_type == "Unknown"
    assert unsafe not in report.model_dump_json()


@pytest.mark.asyncio
async def test_impossible_value_is_blocking() -> None:
    report = await validate(observation(1900))
    plausibility = report.layer(ValidationLayer.PLAUSIBILITY)
    assert plausibility is not None
    assert plausibility.status is LayerStatus.FAILED
    assert plausibility.issues[0].rule_id == "fb-plaus-heart-rate"
    assert report.status is RoutingDecision.REJECT


@pytest.mark.asyncio
async def test_full_mode_runs_all_applicable_layers() -> None:
    report = await validate(
        observation(),
        validator=FakeValidator(),
        terminology=FakeTerminology(),
    )
    for layer in (
        ValidationLayer.STRUCTURAL,
        ValidationLayer.PROFILE,
        ValidationLayer.TERMINOLOGY,
        ValidationLayer.INVARIANTS,
        ValidationLayer.PLAUSIBILITY,
        ValidationLayer.ROUTING,
    ):
        assert report.layer(layer).status is LayerStatus.PASSED  # type: ignore[union-attr]
    assert report.status is RoutingDecision.AUTO


@pytest.mark.asyncio
async def test_dependency_outages_propagate_fail_closed() -> None:
    with pytest.raises(ValidatorUnavailableError):
        await validate(
            observation(),
            validator=FakeValidator(unavailable=True),
            terminology=FakeTerminology(),
        )
    with pytest.raises(TerminologyUnavailableError):
        await validate(
            observation(),
            validator=FakeValidator(),
            terminology=FakeTerminology(unavailable=True),
        )


@pytest.mark.asyncio
async def test_validator_messages_are_not_copied_into_reports() -> None:
    unsafe = "Synthetic Patient Name"
    report = await validate(
        observation(),
        validator=FakeValidator(
            issues=(ValidatorIssue("error", "invalid", unsafe, "Observation.value[x]"),)
        ),
        terminology=FakeTerminology(),
    )

    assert unsafe not in report.model_dump_json()
