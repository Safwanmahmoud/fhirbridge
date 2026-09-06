# Contributing

Use Python 3.11 or newer and synthetic test data only.

```bash
python -m pip install -e ".[dev]"
python -m pip install -e ".[all]"
ruff check .
mypy
pytest
python -m build
twine check dist/*
```

Preserve these invariants:

- never add a clinical code without deterministic terminology verification;
- retain source text when adding coding;
- propagate terminology outages rather than treating them as invalid codes;
- never infer or search for destination identity;
- keep notes, validation messages, and exceptions free of PHI;
- mark unavailable validation layers as skipped and fail closed;
- clear reversible de-identification vaults before returning;
- require explicit acknowledgement and allowlisting for clinical-data egress; and
- keep databases, web frameworks, and EHR submission outside the package.

Open a focused issue or pull request and update tests and public documentation with behavior.

## Releasing to PyPI

The release workflow uses PyPI Trusted Publishing and does not accept an API token.
Before the first release, create a pending publisher on PyPI with:

- project name: `fhiratwill`
- owner: `Safwanmahmoud`
- repository: `fhirbridge`
- workflow: `release.yml`
- environment: `pypi`

Also create a protected GitHub environment named `pypi`. Then:

1. update `__version__` in `src/fhiratwill/__init__.py`;
2. move the release notes in `CHANGELOG.md` under that version;
3. run every command above from a clean checkout;
4. commit and tag the exact version as `v<version>`; and
5. publish the corresponding GitHub Release.

Publishing the GitHub Release triggers one build job and one trusted-publishing job.
Do not upload a locally built artifact or configure a long-lived PyPI credential.
