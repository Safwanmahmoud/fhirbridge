"""PHI-safe de-identification exceptions."""

from fhiratwill.errors import DeidError


class DeidentificationError(DeidError):
    """Base error whose messages must never contain clinical input."""

    code = "deidentification-error"


class PhiMinimizationFailedError(DeidentificationError):
    """Raised when text cannot be safely minimized or restored."""

    code = "phi-minimization-failed"


__all__ = ["DeidentificationError", "PhiMinimizationFailedError"]
