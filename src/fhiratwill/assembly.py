"""Deterministic FHIR bundle assembly from validated entity mappings."""

from __future__ import annotations

import importlib
import re
import types
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Union, get_args, get_origin

from fhiratwill.tags import AI_DERIVED, MACHINE_INFERRED, provenance_tag

_NAMESPACE: Final = uuid.uuid5(uuid.NAMESPACE_URL, "https://fhirbridge.org/bundle-entry")
_TYPE_ORDER = ("Patient", "Practitioner", "Organization", "Encounter", "Condition", "Observation")
_REFERENCE_TARGETS: Mapping[str, str | None] = {
    "subject": "Patient",
    "patient": "Patient",
    "encounter": "Encounter",
    "author": "Practitioner",
    "performer": "Practitioner",
    "requester": "Practitioner",
    "reasonReference": None,
}
_SUBJECT_KEYS = {
    "AllergyIntolerance": "patient",
    "Condition": "subject",
    "DiagnosticReport": "subject",
    "DocumentReference": "subject",
    "Encounter": "subject",
    "Immunization": "patient",
    "MedicationAdministration": "subject",
    "MedicationRequest": "subject",
    "Observation": "subject",
    "Procedure": "subject",
}
_DEFAULTS: Mapping[str, Mapping[str, Any]] = {
    "CarePlan": {"status": "active", "intent": "plan"},
    "DiagnosticReport": {"status": "final"},
    "DocumentReference": {"status": "current"},
    "Encounter": {
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "AMB",
            "display": "ambulatory",
        },
    },
    "ImagingStudy": {"status": "available"},
    "Immunization": {"status": "completed"},
    "MedicationAdministration": {"status": "completed"},
    "MedicationRequest": {"status": "active", "intent": "order"},
    "Observation": {"status": "final"},
    "Procedure": {"status": "completed"},
}
_DATE = re.compile(r"^\d{4}(-(?:0[1-9]|1[0-2])(-(?:0[1-9]|[12]\d|3[01]))?)?$")
_DATETIME = re.compile(
    r"^(?:\d{4}(-(?:0[1-9]|1[0-2])(-(?:0[1-9]|[12]\d|3[01]))?)?|"
    r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])T"
    r"(?:[01]\d|2[0-3]):[0-5]\d:(?:[0-5]\d|60)(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))$"
)
_QUANTITY = re.compile(r"^(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>\S.*)?$")
_COMPOUND = re.compile(r"^-?\d+(?:\.\d+)?\s*/\s*-?\d")


class AssemblyAction(StrEnum):
    DROPPED = "dropped"
    INFERRED = "inferred"
    WIRED = "wired"
    UNRESOLVED = "unresolved"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class AssemblyNote:
    """PHI-free assembly evidence."""

    entry_index: int
    resource_type: str
    element: str
    action: AssemblyAction
    detail: str


@dataclass(frozen=True, slots=True)
class AssembledBundle:
    bundle: dict[str, Any]
    notes: tuple[AssemblyNote, ...]

    @property
    def inferred_entry_indexes(self) -> frozenset[int]:
        return frozenset(
            note.entry_index for note in self.notes if note.action is AssemblyAction.INFERRED
        )


class CoercionError(ValueError):
    pass


def _typed_model(resource_type: str) -> type[Any] | None:
    try:
        module = importlib.import_module(f"fhir.resources.R4B.{resource_type.lower()}")
    except ModuleNotFoundError:
        return None
    model = getattr(module, resource_type, None)
    return model if isinstance(model, type) else None


def _unwrap(annotation: Any) -> tuple[str, bool]:
    origin = get_origin(annotation)
    args = tuple(arg for arg in get_args(annotation) if arg is not type(None))
    if origin in (Union, types.UnionType):
        for arg in args:
            result = _unwrap(arg)
            if result[0] != "unknown":
                return result
        return "unknown", False
    if origin is list:
        name, _ = _unwrap(args[0])
        return name, True
    if hasattr(annotation, "__metadata__"):
        metadata = annotation.__metadata__
        return (type(metadata[0]).__name__, False) if metadata else _unwrap(args[0])
    if isinstance(annotation, type):
        return annotation.__name__.removesuffix("Type"), False
    return "unknown", False


def resolve_datatype(resource_type: str, element: str) -> tuple[str, bool]:
    """Resolve an element's FHIR datatype using the packaged R4B model metadata."""
    model = _typed_model(resource_type)
    if model is None:
        return "unknown", False
    fields = {
        str(field.alias or name): field
        for name, field in model.model_fields.items()
        if not name.endswith("__ext")
    }
    field = fields.get(element)
    return _unwrap(field.annotation) if field else ("unknown", False)


def _temporal(pattern: re.Pattern[str], label: str) -> Callable[[str], str]:
    def convert(value: str) -> str:
        text = value.strip()
        if not pattern.match(text):
            raise CoercionError(f"not a FHIR {label}")
        return text

    return convert


def _quantity(value: str) -> dict[str, Any]:
    text = value.strip()
    if _COMPOUND.match(text):
        raise CoercionError("compound value cannot be represented as one Quantity")
    match = _QUANTITY.match(text)
    if not match:
        raise CoercionError("no leading numeric value")
    raw = match.group("value")
    result: dict[str, Any] = {"value": float(raw) if "." in raw else int(raw)}
    if match.group("unit"):
        result["unit"] = match.group("unit").strip()
    return result


def _name(value: str) -> dict[str, Any]:
    text = value.strip()
    parts = text.split()
    result: dict[str, Any] = {"text": text}
    if len(parts) > 1:
        result.update(family=parts[-1], given=parts[:-1])
    return result


def _text(key: str) -> Callable[[str], dict[str, str]]:
    return lambda value: {key: value.strip()}


def _integer(value: str) -> int:
    try:
        return int(value.strip())
    except ValueError as exc:
        raise CoercionError("not an integer") from exc


_COERCERS: Mapping[str, Callable[[str], Any]] = {
    "Address": _text("text"),
    "Annotation": _text("text"),
    "Code": str.strip,
    "CodeableConcept": _text("text"),
    "Coding": _text("display"),
    "Date": _temporal(_DATE, "date"),
    "DateTime": _temporal(_DATETIME, "dateTime"),
    "Dosage": _text("text"),
    "HumanName": _name,
    "Identifier": _text("value"),
    "Integer": _integer,
    "PositiveInt": _integer,
    "Quantity": _quantity,
    "String": str.strip,
    "UnsignedInt": _integer,
    "bool": lambda value: {"true": True, "false": False, "yes": True, "no": False}[
        value.strip().lower()
    ],
    "Period": lambda value: {"start": _temporal(_DATETIME, "dateTime")(value)},
}


def assemble_bundle(entities: Sequence[Mapping[str, str]], *, seed: str) -> AssembledBundle:
    """Build a deterministic collection Bundle without inventing clinical codes."""
    groups: dict[tuple[str, str], list[Mapping[str, str]]] = {}
    for entity in entities:
        groups.setdefault((entity["resourceType"], entity["instance"]), []).append(entity)
    keys = sorted(
        groups,
        key=lambda key: (
            _TYPE_ORDER.index(key[0]) if key[0] in _TYPE_ORDER else len(_TYPE_ORDER),
            key,
        ),
    )
    urls = {key: f"urn:uuid:{uuid.uuid5(_NAMESPACE, f'{seed}:{key[0]}/{key[1]}')}" for key in keys}
    counts = {kind: sum(key[0] == kind for key in keys) for kind, _ in keys}
    singletons = {kind: urls[key] for key in keys if counts[kind := key[0]] == 1}
    notes: list[AssemblyNote] = []
    entries: list[dict[str, Any]] = []
    for index, key in enumerate(keys):
        resource: dict[str, Any] = {"resourceType": key[0]}

        def note(
            element: str,
            action: AssemblyAction,
            detail: str,
            entry_index: int = index,
            resource_type: str = key[0],
        ) -> None:
            notes.append(AssemblyNote(entry_index, resource_type, element, action, detail))

        for entity in groups[key]:
            element, value = entity["keyword"], entity["value"]
            datatype, is_list = resolve_datatype(key[0], element)
            if datatype == "Reference":
                target = _REFERENCE_TARGETS.get(element)
                target_url = singletons.get(target) if target else None
                placed: Any = (
                    {"reference": target_url} if target_url else {"display": value.strip()}
                )
                if target_url is None:
                    note(element, AssemblyAction.UNRESOLVED, "no unambiguous target; kept as text")
            elif datatype not in _COERCERS:
                note(element, AssemblyAction.DROPPED, f"{datatype} has no single-string form")
                continue
            else:
                try:
                    placed = _COERCERS[datatype](value)
                except (CoercionError, KeyError):
                    note(
                        element,
                        AssemblyAction.DROPPED,
                        f"value is not representable as {datatype}",
                    )
                    continue
            if is_list:
                resource.setdefault(element, []).append(placed)
            elif element in resource:
                note(element, AssemblyAction.CONFLICT, "second scalar value discarded")
            else:
                resource[element] = placed
        subject_key = _SUBJECT_KEYS.get(key[0])
        if subject_key and subject_key not in resource:
            if "Patient" in singletons:
                resource[subject_key] = {"reference": singletons["Patient"]}
                note(subject_key, AssemblyAction.WIRED, "pointed at the only Patient")
            else:
                note(subject_key, AssemblyAction.UNRESOLVED, "no unambiguous Patient")
        for element, default in _DEFAULTS.get(key[0], {}).items():
            if element not in resource:
                resource[element] = default
                note(element, AssemblyAction.INFERRED, "required by FHIR and not stated")
        entries.append({"fullUrl": urls[key], "resource": resource})
    inferred = {note.entry_index for note in notes if note.action is AssemblyAction.INFERRED}
    for index, entry in enumerate(entries):
        tags = [provenance_tag(AI_DERIVED, "Machine-derived")]
        if index in inferred:
            tags.append(provenance_tag(MACHINE_INFERRED, "Required value was inferred"))
        entry["resource"]["meta"] = {"tag": tags}
    return AssembledBundle(
        bundle={"resourceType": "Bundle", "type": "collection", "entry": entries},
        notes=tuple(notes),
    )


__all__ = [
    "AssembledBundle",
    "AssemblyAction",
    "AssemblyNote",
    "CoercionError",
    "assemble_bundle",
    "resolve_datatype",
]
