"""Reviewed exact-match terminology binding with mandatory verification."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from fhiratwill.errors import UnknownValueSetError
from fhiratwill.tags import MACHINE_CODED, provenance_tag
from fhiratwill.terminology import TerminologyClient

BINDING_TABLE_VERSION = "1"
_UCUM = "http://unitsofmeasure.org"


class BindingAction(StrEnum):
    BOUND = "bound"
    UNBOUND = "unbound"
    AMBIGUOUS = "ambiguous"


class BindingNote(BaseModel):
    """PHI-free binding evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    entry_index: int = Field(ge=0)
    resource_type: str
    element: str
    action: BindingAction
    value_set: str | None = None
    candidate_count: int = Field(ge=0)
    detail: str


class BindingCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    eligible: int = Field(ge=0)
    bound: int = Field(ge=0)
    unbound: int = Field(ge=0)
    ambiguous: int = Field(ge=0)


class BoundBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    bundle: dict[str, Any]
    notes: list[BindingNote]
    coverage: BindingCoverage
    table_version: str


@dataclass(frozen=True, slots=True)
class ConceptRule:
    path: str
    system: str
    code: str
    display: str
    value_set: str
    aliases: frozenset[str]


@dataclass(frozen=True, slots=True)
class UnitRule:
    code: str
    display: str
    aliases: frozenset[str]


@dataclass(frozen=True, slots=True)
class ConceptPack:
    version: str
    concepts: tuple[ConceptRule, ...]
    units: tuple[UnitRule, ...]


def normalize_designation(value: str) -> str:
    return " ".join(value.casefold().strip().split())


@lru_cache(maxsize=2)
def load_concepts(path: str | None = None) -> ConceptPack:
    """Load the packaged reviewed table, or an explicit compatible table."""
    text = (
        Path(path).read_text(encoding="utf-8")
        if path
        else files("fhiratwill").joinpath("data/concepts.yaml").read_text(encoding="utf-8")
    )
    raw = yaml.safe_load(text) or {}
    version = str(raw.get("version", ""))
    if version != BINDING_TABLE_VERSION:
        raise ValueError(
            f"concept table version {version!r} does not match {BINDING_TABLE_VERSION!r}"
        )
    concepts = tuple(
        ConceptRule(
            path=str(item["path"]),
            system=str(item["system"]),
            code=str(item["code"]),
            display=str(item["display"]),
            value_set=str(item["value_set"]),
            aliases=frozenset(normalize_designation(str(alias)) for alias in item["aliases"]),
        )
        for item in raw.get("concepts", [])
    )
    units = tuple(
        UnitRule(
            code=str(item["code"]),
            display=str(item["display"]),
            aliases=frozenset(normalize_designation(str(alias)) for alias in item["aliases"]),
        )
        for item in raw.get("units", [])
    )
    return ConceptPack(version, concepts, units)


async def bind_bundle(
    bundle: dict[str, Any],
    *,
    client: TerminologyClient,
    pack: ConceptPack | None = None,
) -> BoundBundle:
    """Return a coded copy; never remove source text or accept an unverified code."""
    rules = pack or load_concepts()
    output = copy.deepcopy(bundle)
    notes: list[BindingNote] = []
    eligible = bound = unbound = ambiguous = 0
    entries = output.get("entry", [])
    if not isinstance(entries, list):
        entries = []
    for entry_index, entry in enumerate(entries):
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(resource, dict):
            continue
        resource_type = str(resource.get("resourceType", ""))
        resource_bound = False
        for element, value in list(resource.items()):
            path = f"{resource_type}.{element}"
            if (
                isinstance(value, dict)
                and isinstance(value.get("text"), str)
                and not value.get("coding")
            ):
                eligible += 1
                action, count, value_set = await _bind_concept(value, path, client, rules)
                notes.append(_note(entry_index, resource_type, element, action, count, value_set))
                bound += action is BindingAction.BOUND
                unbound += action is BindingAction.UNBOUND
                ambiguous += action is BindingAction.AMBIGUOUS
                resource_bound |= action is BindingAction.BOUND
            if element.startswith("value") and isinstance(value, dict):
                unit = value.get("unit")
                if isinstance(unit, str) and not value.get("code"):
                    eligible += 1
                    action, count = await _bind_unit(value, unit, client, rules)
                    notes.append(_note(entry_index, resource_type, element, action, count, None))
                    bound += action is BindingAction.BOUND
                    unbound += action is BindingAction.UNBOUND
                    ambiguous += action is BindingAction.AMBIGUOUS
                    resource_bound |= action is BindingAction.BOUND
        if resource_bound:
            resource.setdefault("meta", {}).setdefault("tag", []).append(
                provenance_tag(MACHINE_CODED, "Terminology-verified deterministic coding")
            )
    return BoundBundle(
        bundle=output,
        notes=notes,
        coverage=BindingCoverage(
            eligible=eligible, bound=bound, unbound=unbound, ambiguous=ambiguous
        ),
        table_version=rules.version,
    )


def _note(
    entry_index: int,
    resource_type: str,
    element: str,
    action: BindingAction,
    count: int,
    value_set: str | None,
) -> BindingNote:
    details = {
        BindingAction.BOUND: "candidate verified and applied",
        BindingAction.UNBOUND: "no single verified candidate",
        BindingAction.AMBIGUOUS: "multiple exact candidates; coding refused",
    }
    return BindingNote(
        entry_index=entry_index,
        resource_type=resource_type,
        element=element,
        action=action,
        candidate_count=count,
        value_set=value_set,
        detail=details[action],
    )


async def _bind_concept(
    concept: dict[str, Any],
    path: str,
    client: TerminologyClient,
    pack: ConceptPack,
) -> tuple[BindingAction, int, str | None]:
    text = normalize_designation(str(concept["text"]))
    candidates = [rule for rule in pack.concepts if rule.path == path and text in rule.aliases]
    value_set = next((rule.value_set for rule in pack.concepts if rule.path == path), None)
    if not candidates and value_set:
        try:
            expansion = await client.expand(value_set=value_set, filter_text=text, count=10)
        except UnknownValueSetError:
            return BindingAction.UNBOUND, 0, value_set
        exact = [
            coding
            for coding in expansion.contains
            if coding.display and normalize_designation(coding.display) == text
        ]
        if len(exact) > 1:
            return BindingAction.AMBIGUOUS, len(exact), value_set
        if len(exact) == 1 and exact[0].system and exact[0].code:
            coding = exact[0]
            assert coding.system is not None
            assert coding.code is not None
            candidates = [
                ConceptRule(
                    path,
                    coding.system,
                    coding.code,
                    coding.display or text,
                    value_set,
                    frozenset({text}),
                )
            ]
    if len(candidates) > 1:
        return BindingAction.AMBIGUOUS, len(candidates), value_set
    if not candidates:
        return BindingAction.UNBOUND, 0, value_set
    candidate = candidates[0]
    try:
        verified = await client.validate_code(
            system=candidate.system,
            code=candidate.code,
            display=candidate.display,
            value_set=candidate.value_set,
        )
    except UnknownValueSetError:
        return BindingAction.UNBOUND, 1, value_set
    if not verified.result:
        return BindingAction.UNBOUND, 1, value_set
    concept["coding"] = [
        {
            "system": candidate.system,
            "code": candidate.code,
            "display": verified.display or candidate.display,
            "userSelected": False,
        }
    ]
    return BindingAction.BOUND, 1, value_set


async def _bind_unit(
    quantity: dict[str, Any], unit: str, client: TerminologyClient, pack: ConceptPack
) -> tuple[BindingAction, int]:
    matches = [rule for rule in pack.units if normalize_designation(unit) in rule.aliases]
    if len(matches) != 1:
        action = BindingAction.AMBIGUOUS if matches else BindingAction.UNBOUND
        return action, len(matches)
    candidate = matches[0]
    verified = await client.validate_code(system=_UCUM, code=candidate.code)
    if not verified.result:
        return BindingAction.UNBOUND, 1
    quantity.update(system=_UCUM, code=candidate.code, unit=candidate.display)
    return BindingAction.BOUND, 1


__all__ = [
    "BINDING_TABLE_VERSION",
    "BindingAction",
    "BindingCoverage",
    "BindingNote",
    "BoundBundle",
    "ConceptPack",
    "ConceptRule",
    "UnitRule",
    "bind_bundle",
    "load_concepts",
    "normalize_designation",
]
