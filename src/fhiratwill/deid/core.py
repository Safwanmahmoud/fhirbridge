"""Narrative minimization with request-local reversible state."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fhiratwill.deid.detectors import Detector, build_detectors, load_pattern_rules
from fhiratwill.deid.models import (
    NOOP_DEID_OBSERVER,
    DeclaredIdentifier,
    DeidentifyResult,
    DeidMode,
    DeidObserver,
    DeidPolicy,
)
from fhiratwill.deid.spans import resolve_overlaps
from fhiratwill.deid.vault import Vault


@dataclass(slots=True)
class Minimization:
    """Internal PHI-bearing state. Always close it in a finally block."""

    safe_text: str
    policy: DeidPolicy
    vault: Vault
    detections: dict[str, int]
    applied: bool
    observer: DeidObserver = NOOP_DEID_OBSERVER
    restored: int = 0

    def assert_safe_payload(self, payload: Any) -> None:
        if self.policy.enforced and not self.applied:
            raise ValueError("enforced de-identification was not applied")
        if self.policy.enforced:
            self.vault.assert_originals_absent(payload)

    def restore_entities(self, entities: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
        restored_entities: list[dict[str, str]] = []
        for entity in entities:
            value = entity["value"]
            restored = self.vault.restore(value)
            self.restored += int(restored != value)
            self.vault.assert_surrogates_absent(restored)
            restored_entities.append({**entity, "value": restored})
        return restored_entities

    def result(self) -> DeidentifyResult:
        result = DeidentifyResult(
            text=self.safe_text,
            mode=self.policy.mode,
            profile=self.policy.profile,
            ruleset_version=load_pattern_rules()[0],
            detections=dict(sorted(self.detections.items())),
            replacements=self.vault.size,
        )
        self.observer.observe(
            mode=result.mode,
            detections=result.detections,
            replacements=result.replacements,
        )
        return result

    def close(self) -> None:
        self.vault.clear()


def minimize(
    text: str,
    *,
    policy: DeidPolicy,
    known_identifiers: Sequence[DeclaredIdentifier] = (),
    detectors: Sequence[Detector] | None = None,
    observer: DeidObserver = NOOP_DEID_OBSERVER,
) -> Minimization:
    if policy.mode is DeidMode.OFF:
        return Minimization(text, policy, Vault(), {}, False, observer)
    active = (
        tuple(detectors)
        if detectors is not None
        else build_detectors(policy.profile, known_identifiers)
    )
    spans = resolve_overlaps(span for detector in active for span in detector.detect(text))
    counts = Counter(str(span.identifier_class) for span in spans)
    if policy.mode is DeidMode.ADVISORY:
        return Minimization(text, policy, Vault(), dict(counts), False, observer)
    vault = Vault()
    safe = text
    for span in reversed(spans):
        original = text[span.start : span.end]
        surrogate = vault.surrogate_for(original, span.identifier_class)
        safe = f"{safe[: span.start]}{surrogate}{safe[span.end :]}"
    return Minimization(safe, policy, vault, dict(counts), True, observer)


def deidentify(
    text: str,
    *,
    policy: DeidPolicy | None = None,
    known_identifiers: Sequence[DeclaredIdentifier] = (),
    observer: DeidObserver = NOOP_DEID_OBSERVER,
) -> DeidentifyResult:
    """De-identify text synchronously; enforced Safe Harbor is the default."""
    minimization = minimize(
        text,
        policy=policy or DeidPolicy(),
        known_identifiers=known_identifiers,
        observer=observer,
    )
    try:
        return minimization.result()
    finally:
        minimization.close()


__all__ = ["Minimization", "deidentify", "minimize"]
