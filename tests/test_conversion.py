from __future__ import annotations

import pytest
from pydantic import SecretStr

from fhiratwill.conversion import (
    PROMPT_FINGERPRINT,
    REVIEWED_PROMPT_FINGERPRINT,
    EgressPolicyError,
    ExtractionSchemaError,
    LlmInvocation,
    SpeechInvocation,
    parse_entities,
    text2fhir,
    voice2fhir,
)
from fhiratwill.conversion.prompts import NARRATIVE_TO_ENTITIES
from fhiratwill.deid import DeclaredIdentifier, IdentifierClass
from fhiratwill.validation import RoutingDecision, ValidationLayer
from tests.conversion_fakes import FakeLlmClient, FakeSpeechClient


def test_strict_extraction_rejects_extra_and_unknown_fields() -> None:
    with pytest.raises(ExtractionSchemaError):
        parse_entities(
            {
                "entities": [
                    {
                        "resourceType": "Patient",
                        "keyword": "notAKey",
                        "value": "synthetic",
                        "extra": "forbidden",
                    }
                ]
            }
        )


def test_parse_entities_assigns_instances_without_model_slugs() -> None:
    entities = parse_entities(
        {
            "entities": [
                {"resourceType": "Patient", "keyword": "name", "value": "James Example"},
                {"resourceType": "Patient", "keyword": "birthDate", "value": "2014-03-12"},
                {"resourceType": "Observation", "keyword": "code", "value": "temperature"},
                {"resourceType": "Observation", "keyword": "valueQuantity", "value": "38.2 C"},
                {"resourceType": "Observation", "keyword": "code", "value": "heart rate"},
                {"resourceType": "Observation", "keyword": "valueQuantity", "value": "72 /min"},
            ]
        }
    )
    assert [item["instance"] for item in entities] == [
        "patient",
        "patient",
        "observation-1",
        "observation-1",
        "observation-2",
        "observation-2",
    ]
    assert all("instance" in item for item in entities)


def test_parse_entities_ignores_model_supplied_instance() -> None:
    entities = parse_entities(
        {
            "entities": [
                {
                    "resourceType": "Patient",
                    "instance": "james-example",
                    "keyword": "gender",
                    "value": "male",
                }
            ]
        }
    )
    assert entities == [
        {
            "resourceType": "Patient",
            "instance": "patient",
            "keyword": "gender",
            "value": "male",
        }
    ]


def test_prompt_set_matches_reviewed_fingerprint() -> None:
    assert PROMPT_FINGERPRINT == REVIEWED_PROMPT_FINGERPRINT


def test_extraction_prompt_requires_name_and_observation_code() -> None:
    prompt = NARRATIVE_TO_ENTITIES.system
    assert "emit Patient.name" in prompt
    assert "do not skip Observation.code" in prompt
    assert '"keyword":"name"' in prompt
    assert '"keyword":"code"' in prompt


@pytest.mark.asyncio
async def test_text_extracts_minimized_input_then_restores() -> None:
    llm = FakeLlmClient()
    invocation = LlmInvocation("fake", "fake/model", SecretStr("fake-secret"))

    result = await text2fhir(
        "Jane Synthetic reports pain.",
        llm=llm,
        invocation=invocation,
        seed="conversion-1",
        known_identifiers=(DeclaredIdentifier(IdentifierClass.NAME, "Jane Synthetic"),),
    )

    assert "Jane Synthetic" not in llm.calls[0]
    assert "[[NAME_" in llm.calls[0]
    assert result.bundle["entry"][0]["resource"]["name"][0]["text"] == "Jane Synthetic"
    assert result.prompt_fingerprint
    assert len(result.validation.layers) == len(ValidationLayer)
    assert result.validation.status is RoutingDecision.NEEDS_REVIEW


@pytest.mark.asyncio
async def test_voice_transcribes_once_then_uses_text_pipeline() -> None:
    speech = FakeSpeechClient("Patient reports pain.")
    llm = FakeLlmClient()

    result = await voice2fhir(
        b"synthetic-audio",
        media_type="audio/wav",
        speech=speech,
        speech_invocation=SpeechInvocation(
            "local",
            "fake/stt",
            SecretStr("fake-speech-secret"),
            base_url="http://127.0.0.1:8001",
        ),
        llm=llm,
        llm_invocation=LlmInvocation("local", "fake/model", SecretStr("fake-llm-secret")),
        seed="conversion-2",
    )

    assert speech.calls == 1
    assert len(llm.calls) == 1
    assert result.transcript == "Patient reports pain."


@pytest.mark.asyncio
async def test_voice_blocks_external_audio_before_transcription() -> None:
    speech = FakeSpeechClient("Patient reports pain.")

    with pytest.raises(EgressPolicyError):
        await voice2fhir(
            b"synthetic-audio",
            media_type="audio/wav",
            speech=speech,
            speech_invocation=SpeechInvocation(
                "external",
                "fake/stt",
                SecretStr("fake-speech-secret"),
                base_url="https://speech.example.test",
                phi_egress_acknowledged=True,
            ),
            llm=FakeLlmClient(),
            llm_invocation=LlmInvocation("local", "fake/model", SecretStr("fake-secret")),
            seed="conversion-3",
        )

    assert speech.calls == 0
