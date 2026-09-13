"""Versioned, fingerprinted prompts for grounded extraction and dictation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

from fhiratwill.conversion.extraction import resource_catalog_text

PROMPT_SET_VERSION: Final = "2"


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    id: str
    system: str
    user_template: str

    def render_user(self, **values: str) -> str:
        return self.user_template.format(**values)


NARRATIVE_TO_ENTITIES: Final = PromptTemplate(
    id="text2fhir_extract_entities",
    system=(
        "Extract only explicitly stated clinical and demographic facts. Return exactly one "
        "JSON object containing only an `entities` array. Every item must contain exactly "
        "`resourceType`, `keyword`, and `value`, all nonempty strings. "
        "`resourceType` and `keyword` must match the catalog. Do not emit `instance` or any "
        "other keys; grouping is assigned after extraction. Preserve source wording and every "
        "[[CLASS_TOKEN]] exactly. Never invent unstated facts, diagnoses, or terminology codes "
        "(for example LOINC). Represent each fact as a separate item.\n\n"
        "Names, what was measured, and readings are facts when the narrative states them. "
        "Do not skip a name because it identifies the subject, and do not skip Observation.code "
        "because the numeric value seems enough.\n"
        "- If a person's name is stated, including a [[NAME_...]] token, emit Patient.name.\n"
        "- If sex or gender is stated, emit Patient.gender. If a birth date is stated, emit "
        "Patient.birthDate.\n"
        "- If a measurement is stated, emit Observation.code with the source name of the "
        "measurement (for example temperature) and Observation.valueQuantity or valueString "
        "with the reading and unit.\n\n"
        "Example for 'Ada Example is female with a temperature of 38.2 C':\n"
        '{"entities":[{"resourceType":"Patient","keyword":"name","value":"Ada Example"},'
        '{"resourceType":"Patient","keyword":"gender","value":"female"},'
        '{"resourceType":"Observation","keyword":"code","value":"temperature"},'
        '{"resourceType":"Observation","keyword":"valueQuantity","value":"38.2 C"}]}\n\n'
        "Catalog:\n" + resource_catalog_text()
    ),
    user_template="Extract grounded FHIR entities.\n\nClinical narrative:\n{narrative}",
)

DICTATION_TRANSCRIBE: Final = PromptTemplate(
    id="voice2fhir_dictation_transcribe",
    system=(
        "Transcribe medical dictation verbatim into plain text. Preserve negation, quantities, "
        "and units. Use [inaudible] rather than guessing. Add no commentary."
    ),
    user_template="",
)

PROMPT_SET: Final = (DICTATION_TRANSCRIBE, NARRATIVE_TO_ENTITIES)


def prompt_set_fingerprint() -> str:
    digest = hashlib.sha256()
    for template in sorted(PROMPT_SET, key=lambda item: item.id):
        for value in (template.id, template.system, template.user_template):
            digest.update(value.encode())
            digest.update(b"\x00")
    return digest.hexdigest()


REVIEWED_PROMPT_FINGERPRINT: Final = (
    "a90d3832adcf220b10657af6bdde903439d12f9bdf2a98f660edc733a6b46411"
)
PROMPT_FINGERPRINT: Final = prompt_set_fingerprint()
if PROMPT_FINGERPRINT != REVIEWED_PROMPT_FINGERPRINT:
    raise RuntimeError("prompt set does not match the reviewed fingerprint")

__all__ = [
    "DICTATION_TRANSCRIBE",
    "NARRATIVE_TO_ENTITIES",
    "PROMPT_FINGERPRINT",
    "PROMPT_SET_VERSION",
    "REVIEWED_PROMPT_FINGERPRINT",
    "PromptTemplate",
    "prompt_set_fingerprint",
]
