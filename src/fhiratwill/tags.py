"""Machine provenance tags used by generated resources."""

from typing import Final

PROVENANCE_TAG_SYSTEM: Final = "https://fhirbridge.org/CodeSystem/provenance-tags"
AI_DERIVED: Final = "ai-derived"
MACHINE_INFERRED: Final = "machine-inferred"
MACHINE_CODED: Final = "machine-coded"


def provenance_tag(code: str, display: str | None = None) -> dict[str, str]:
    coding = {"system": PROVENANCE_TAG_SYSTEM, "code": code}
    if display is not None:
        coding["display"] = display
    return coding


__all__ = [
    "AI_DERIVED",
    "MACHINE_CODED",
    "MACHINE_INFERRED",
    "PROVENANCE_TAG_SYSTEM",
    "provenance_tag",
]
