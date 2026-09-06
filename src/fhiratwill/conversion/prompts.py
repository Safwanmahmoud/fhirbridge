"""Versioned, fingerprinted prompts for grounded extraction and dictation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

from fhiratwill.conversion.extraction import resource_catalog_text

PROMPT_SET_VERSION: Final = "1"


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
        "`resourceType`, `instance`, `keyword`, and `value`, all nonempty strings. "
        "`resourceType` and `keyword` must match the catalog. `instance` must be a lowercase "
        "letters/digits/hyphens slug that groups facts about one thing and contains no "
        "identifying detail. Preserve source wording and every [[CLASS_TOKEN]] exactly. "
        "Never infer facts or clinical codes. Represent each fact as a separate item.\n\n"
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
    "39fcb5d790bbcac452eb58607a382bcc23bc11ac6fc87590904482928b32266f"
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
