from __future__ import annotations

from collections.abc import Mapping

import pytest

from fhiratwill.deid import DeclaredIdentifier, DeidMode, IdentifierClass, deidentify
from fhiratwill.deid.vault import Vault


def test_deidentify_is_enforced_and_uses_known_identifiers() -> None:
    result = deidentify(
        "Jane Synthetic called 415-555-1212.",
        known_identifiers=(DeclaredIdentifier(IdentifierClass.NAME, "Jane Synthetic"),),
    )

    assert "Jane Synthetic" not in result.text
    assert "415-555-1212" not in result.text
    assert result.replacements == 2
    assert result.mode == "enforced"
    assert result.notes == ()


def test_deidentify_always_clears_request_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    cleared: list[int] = []
    original = Vault.clear

    def observe_clear(vault: Vault) -> None:
        original(vault)
        cleared.append(vault.size)

    monkeypatch.setattr(Vault, "clear", observe_clear)
    deidentify(
        "Jane Synthetic reports pain.",
        known_identifiers=(DeclaredIdentifier(IdentifierClass.NAME, "Jane Synthetic"),),
    )

    assert cleared == [0]


def test_observer_receives_counts_without_narrative() -> None:
    observed: list[tuple[dict[str, int], int]] = []

    class Observer:
        def observe(
            self,
            *,
            mode: DeidMode,
            detections: Mapping[str, int],
            replacements: int,
        ) -> None:
            del mode
            observed.append((dict(detections), replacements))

    deidentify("call 415-555-1212.", observer=Observer())

    assert observed == [({"phone": 1}, 1)]
