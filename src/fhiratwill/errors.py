"""Small, PHI-safe exception hierarchy for fail-closed core operations."""

from __future__ import annotations


class FhiratwillError(Exception):
    """Base error. Messages must be developer-authored and contain no clinical values."""


class TerminologyError(FhiratwillError):
    """Base class for deterministic terminology failures."""


class TerminologyUnavailableError(TerminologyError):
    """The terminology adapter could not provide an authoritative answer."""


class UnknownValueSetError(TerminologyError):
    """The terminology adapter does not know the requested ValueSet."""


class TargetUnavailableError(FhiratwillError):
    """The destination adapter could not read the caller-supplied context."""


__all__ = [
    "FhiratwillError",
    "TargetUnavailableError",
    "TerminologyError",
    "TerminologyUnavailableError",
    "UnknownValueSetError",
]
