# fhiratwill

Deterministic, transport-neutral building blocks for assembling, terminology-binding,
context-rebinding, and planning writes of FHIR R4 resources.

> Alpha software. Generated resources remain untrusted until independently validated and
> reviewed for the intended clinical workflow.

## Install

```bash
pip install fhiratwill
```

Python 3.11 or newer is required.

## Assemble deterministically

```python
from fhiratwill import assemble_bundle

entities = [
    {"resourceType": "Patient", "instance": "subject", "keyword": "gender", "value": "female"},
    {"resourceType": "Observation", "instance": "pulse", "keyword": "code", "value": "heart rate"},
    {
        "resourceType": "Observation",
        "instance": "pulse",
        "keyword": "valueQuantity",
        "value": "72/min",
    },
]
result = assemble_bundle(entities, seed="conversion-123")
bundle = result.bundle
```

Assembly keeps coded concepts as text, refuses unsafe coercions, records PHI-free notes,
and produces stable UUIDs for a stable seed. It does not validate clinical truth.

## Bind using your terminology adapter

Implement the async `TerminologyClient` protocol for your terminology service. The library
contains no HTTP client, URL, authentication, or credentials.

```python
from fhiratwill import TerminologyClient, bind_bundle


async def bind(bundle: dict, terminology: TerminologyClient) -> dict:
    result = await bind_bundle(bundle, client=terminology)
    return result.bundle
```

Binding uses exact aliases from the packaged, reviewed `concepts.yaml`; it performs no
fuzzy or model-based coding. A candidate is added only after the adapter verifies it.
Original `CodeableConcept.text` is retained. Adapters must raise
`TerminologyUnavailableError` when no authoritative answer is available; outages
propagate and fail closed.

## Rebind and compile a write plan

```python
from fhiratwill import (
    GENERIC_FHIR_TARGET,
    SubjectContext,
    compile_write_plan,
    rebind_bundle,
)

context = SubjectContext(patient_ref="Patient/123", encounter_ref="Encounter/456")
rebound, notes = rebind_bundle(bundle, context)
plan = compile_write_plan(
    bundle=bundle,
    context=context,
    conversion_id="conversion-123",
    tenant_id="tenant-7",
    descriptor=GENERIC_FHIR_TARGET,
)
```

Generated Patient and Encounter resources are always excluded. References are rebound only
to caller-supplied context. The optional preflight adapter supports direct reads only—never
identity search. Write plans contain deterministic idempotency keys and, when supported by
the descriptor, a FHIR transaction Bundle.

## Scope

This library:

- assembles grounded entity mappings into deterministic FHIR resources;
- verifies exact terminology candidates through a caller-provided adapter;
- checks and rebinds caller-supplied subject context; and
- compiles destination-neutral write plans.

This library does **not** submit data, authenticate to an EHR, host a terminology service,
perform target HTTP calls, validate full FHIR conformance, provide clinical decision
support, or establish HIPAA, GDPR, medical-device, or other regulatory compliance.

## Development

```bash
python -m pip install -e ".[dev]"
ruff check .
mypy
pytest
python -m build
twine check dist/*
```

No publishing command is part of the development workflow. See `CONTRIBUTING.md` and
`SECURITY.md` before contributing.

## License

Apache License 2.0.