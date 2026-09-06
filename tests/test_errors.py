from __future__ import annotations

import pytest

from fhiratwill.errors import FhiratwillError, TerminologyUnavailableError


def test_errors_have_stable_codes_and_immutable_safe_context() -> None:
    error = TerminologyUnavailableError(
        "terminology adapter unavailable",
        safe_context={"provider": "synthetic"},
        retry_after_s=5,
    )

    assert isinstance(error, FhiratwillError)
    assert error.code == "terminology-unavailable"
    assert error.safe_context == {"provider": "synthetic"}
    assert error.retry_after_s == 5
    with pytest.raises(TypeError):
        error.safe_context["provider"] = "changed"  # type: ignore[index]
