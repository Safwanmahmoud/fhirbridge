"""Generic destination capability descriptors; no transport or credentials."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

TARGET_DESCRIPTOR_VERSION = "v1"


class FailurePolicy(StrEnum):
    ATOMIC_TRANSACTION = "atomic_transaction"
    STOP_ON_FIRST_ERROR = "stop_on_first_error"


@runtime_checkable
class TargetDescriptor(Protocol):
    @property
    def target_id(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def supports_transaction(self) -> bool: ...

    @property
    def failure_policy(self) -> FailurePolicy: ...

    @property
    def accepted_resource_types(self) -> frozenset[str] | None: ...

    @property
    def forbidden_elements(self) -> Mapping[str, frozenset[str]]: ...

    def accepts(self, resource_type: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class GenericFhirTarget:
    target_id: str = "generic-fhir-r4"
    version: str = TARGET_DESCRIPTOR_VERSION
    supports_transaction: bool = True
    failure_policy: FailurePolicy = FailurePolicy.ATOMIC_TRANSACTION
    accepted_resource_types: frozenset[str] | None = None
    forbidden_elements: Mapping[str, frozenset[str]] = field(default_factory=dict)

    def accepts(self, resource_type: str) -> bool:
        return self.accepted_resource_types is None or resource_type in self.accepted_resource_types


GENERIC_FHIR_TARGET = GenericFhirTarget()

__all__ = [
    "GENERIC_FHIR_TARGET",
    "TARGET_DESCRIPTOR_VERSION",
    "FailurePolicy",
    "GenericFhirTarget",
    "TargetDescriptor",
]
