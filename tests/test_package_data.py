from __future__ import annotations

from importlib.resources import files

import pytest


@pytest.mark.parametrize(
    ("package", "path"),
    [
        ("fhiratwill", "data/concepts.yaml"),
        ("fhiratwill.deid", "data/allowlist.txt"),
        ("fhiratwill.deid", "data/clinical_eponyms.txt"),
        ("fhiratwill.deid", "data/locations.txt"),
        ("fhiratwill.deid", "rules/identifiers.yaml"),
        ("fhiratwill.validation", "rules/bindings.yaml"),
        ("fhiratwill.validation", "rules/invariants.yaml"),
        ("fhiratwill.validation", "rules/plausibility.yaml"),
    ],
)
def test_reviewed_package_data_is_installed(package: str, path: str) -> None:
    assert files(package).joinpath(path).is_file()
