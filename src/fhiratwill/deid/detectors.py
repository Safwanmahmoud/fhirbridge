"""Deterministic identifier detectors backed by packaged assets."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import cache, lru_cache
from importlib.resources import files
from typing import Any, Final, Protocol

import yaml

from fhiratwill.deid.models import DeclaredIdentifier, DeidProfile, IdentifierClass
from fhiratwill.deid.spans import Span

_WORD_RE: Final = re.compile(r"\b[A-Z][A-Za-z'-]{1,}\b")


class Detector(Protocol):
    name: str
    version: str

    def detect(self, text: str) -> Sequence[Span]: ...


@dataclass(frozen=True, slots=True)
class PatternRule:
    id: str
    identifier_class: IdentifierClass
    pattern: re.Pattern[str]


@lru_cache(maxsize=1)
def load_pattern_rules() -> tuple[str, tuple[PatternRule, ...]]:
    text = files("fhiratwill.deid").joinpath("rules/identifiers.yaml").read_text(encoding="utf-8")
    raw: Any = yaml.safe_load(text)
    if not isinstance(raw, dict) or not isinstance(raw.get("version"), int):
        raise ValueError("de-identification rule pack requires an integer version")
    items = raw.get("patterns")
    if not isinstance(items, list):
        raise ValueError("de-identification rule pack requires a patterns list")
    rules: list[PatternRule] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each de-identification pattern must be an object")
        flags = re.IGNORECASE if "ignorecase" in item.get("flags", []) else 0
        rules.append(
            PatternRule(
                id=str(item["id"]),
                identifier_class=IdentifierClass(str(item["class"])),
                pattern=re.compile(str(item["regex"]), flags),
            )
        )
    return str(raw["version"]), tuple(rules)


@cache
def load_word_set(filename: str) -> frozenset[str]:
    text = files("fhiratwill.deid").joinpath(f"data/{filename}").read_text(encoding="utf-8")
    return frozenset(
        line.strip().casefold()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


@dataclass(slots=True)
class DeclaredIdentifierDetector:
    identifiers: Sequence[DeclaredIdentifier]
    name: str = "declared"
    version: str = "1"

    def detect(self, text: str) -> Sequence[Span]:
        spans: list[Span] = []
        for declared in self.identifiers:
            for variant in _variants(declared):
                pattern = re.compile(rf"(?<!\w){re.escape(variant)}(?:'s)?(?!\w)", re.IGNORECASE)
                spans.extend(
                    Span(match.start(), match.end(), declared.identifier_class, self.name)
                    for match in pattern.finditer(text)
                )
        return spans


@dataclass(slots=True)
class PatternDetector:
    profile: DeidProfile
    rules: Sequence[PatternRule] = field(default_factory=lambda: load_pattern_rules()[1])
    name: str = "pattern"
    version: str = field(default_factory=lambda: load_pattern_rules()[0])

    def detect(self, text: str) -> Sequence[Span]:
        blocked = None
        if self.profile is DeidProfile.HIPAA_LIMITED_DATA_SET:
            blocked = {
                IdentifierClass.EMAIL,
                IdentifierClass.URL,
                IdentifierClass.IP,
                IdentifierClass.SSN,
                IdentifierClass.PHONE,
                IdentifierClass.MRN,
                IdentifierClass.ACCOUNT,
                IdentifierClass.LICENSE,
                IdentifierClass.DEVICE,
            }
        return [
            Span(match.start(), match.end(), rule.identifier_class, self.name)
            for rule in self.rules
            if blocked is None or rule.identifier_class in blocked
            for match in rule.pattern.finditer(text)
        ]


@dataclass(slots=True)
class GazetteerDetector:
    terms: frozenset[str] = field(default_factory=lambda: load_word_set("locations.txt"))
    name: str = "gazetteer"
    version: str = "1"

    def detect(self, text: str) -> Sequence[Span]:
        return [
            Span(match.start(), match.end(), IdentifierClass.LOCATION, self.name)
            for term in sorted(self.terms, key=len, reverse=True)
            for match in re.finditer(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE)
        ]


@dataclass(slots=True)
class UnknownProperNounDetector:
    allowlist: frozenset[str] = field(default_factory=lambda: load_word_set("allowlist.txt"))
    protected_phrases: frozenset[str] = field(
        default_factory=lambda: load_word_set("clinical_eponyms.txt")
    )
    name: str = "unknown_proper_noun"
    version: str = "1"

    def detect(self, text: str) -> Sequence[Span]:
        protected = _phrase_ranges(text, self.protected_phrases)
        return [
            Span(match.start(), match.end(), IdentifierClass.NAME, self.name)
            for match in _WORD_RE.finditer(text)
            if match.group(0).casefold() not in self.allowlist
            and not _inside(match.start(), match.end(), protected)
        ]


def build_detectors(
    profile: DeidProfile, declared: Sequence[DeclaredIdentifier] = ()
) -> tuple[Detector, ...]:
    detectors: list[Detector] = [DeclaredIdentifierDetector(declared), PatternDetector(profile)]
    if profile is DeidProfile.HIPAA_SAFE_HARBOR:
        detectors.extend((GazetteerDetector(), UnknownProperNounDetector()))
    return tuple(detectors)


def _variants(declared: DeclaredIdentifier) -> frozenset[str]:
    value = " ".join(declared.value.split())
    variants = {value}
    if declared.identifier_class is IdentifierClass.NAME:
        parts = value.replace(",", " ").split()
        if len(parts) >= 2:
            variants.update(
                {
                    " ".join(reversed(parts)),
                    f"{parts[0][0]}. {parts[-1]}",
                    f"{parts[0][0]} {parts[-1]}",
                }
            )
    return frozenset(item for item in variants if item)


def _phrase_ranges(text: str, phrases: Iterable[str]) -> list[tuple[int, int]]:
    return [
        (match.start(), match.end())
        for phrase in phrases
        for match in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE)
    ]


def _inside(start: int, end: int, ranges: Iterable[tuple[int, int]]) -> bool:
    return any(left <= start and end <= right for left, right in ranges)


__all__ = ["Detector", "build_detectors", "load_pattern_rules", "load_word_set"]
