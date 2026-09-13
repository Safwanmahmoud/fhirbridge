# fhiratwill

[![PyPI Downloads](https://static.pepy.tech/personalized-badge/fhiratwill?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/fhiratwill)

The Python library behind **FHIR at Will**. Safety-focused, framework-neutral
tools for converting narrative text and audio to FHIR R4, de-identifying
narrative, validating resources, binding terminology, and planning writes.

This repository is the processor. The self-hostable HTTP API, Docker image,
Railway deploy, API keys, and validator sidecar live in
[**FHIR-At-Will**](https://github.com/Safwanmahmoud/FHIR-It-Will).

> Alpha software. Generated resources remain untrusted until independently validated and
> reviewed for the intended clinical workflow.

## This library vs the production API

These two repositories are the same product, split for different jobs:

| You want | Use |
|---|---|
| `pip install` and call `text2fhir` / `validate` from your own code | **This repo** — PyPI package [`fhiratwill`](https://pypi.org/project/fhiratwill/) |
| A self-hostable HTTP API, Docker/Railway images, API keys, HL7 validator sidecar | **[FHIR-It-Will](https://github.com/Safwanmahmoud/FHIR-It-Will)** |

The production API depends on this package and wraps it with FastAPI, auth,
PostgreSQL RLS, BYOK policy headers, sidecar transport, and delivery submission.
Algorithm questions belong here. Deploy, auth, and HTTP contract questions belong
in the [API README](https://github.com/Safwanmahmoud/FHIR-It-Will#readme).

| Name | What it is |
|---|---|
| **FHIR at Will** | Public product |
| **This repository** ([fhirbridge](https://github.com/Safwanmahmoud/fhirbridge)) | Source for the installable library |
| **`fhiratwill`** | PyPI package and `import` name (`from fhiratwill import ...`) |
| **[FHIR-It-Will](https://github.com/Safwanmahmoud/FHIR-It-Will)** | Production HTTP API repository |
| **`fhirbridge`** | The API service's package, container, and API title — not this library |

## Install

```bash
pip install fhiratwill
# Optional LiteLLM text, speech, or both:
pip install "fhiratwill[llm]"
pip install "fhiratwill[voice]"
pip install "fhiratwill[all]"
```

Python 3.11 or newer is required. The base install performs no network I/O and includes no
web framework, database, EHR client, or model provider SDK.

## How processing works

### Validation cascade

`validate` always returns all eight layers. A check that could not run is marked
`skipped` or `not_applicable`; it is never allowed to look like a pass.

| Layer | Check | Local mode (no adapters) |
|---:|---|---|
| L1 | Structural FHIR R4 parsing and resource allowlist | Runs here |
| L2 | Declared and requested profile conformance | `skipped` unless you inject a `ValidatorClient` |
| L3 | Code validity and ValueSet bindings | `skipped` unless you inject a `TerminologyClient` |
| L4 | FHIRPath invariants | `skipped` unless you inject a `ValidatorClient` |
| L5 | Physiological, temporal, and dose plausibility | Runs here |
| L6 | Source-to-output fidelity | `not_applicable` until a source document exists |
| L7 | Omitted clinical mention coverage | `not_applicable` until a source document exists |
| L8 | Auto-accept, review, or reject routing | Runs from available signals; never auto-accepts while a required layer was skipped |

`conformant` is `true` when no blocking issue was found by a layer that ran.
`status` is `auto`, `needs_review`, or `reject`. A structurally valid heart rate
of `44000 /min` is still rejected by L5 as physiologically impossible.

The [production API](https://github.com/Safwanmahmoud/FHIR-It-Will) injects the
HL7 validator sidecar and a terminology-server adapter so L2–L4 can run over
HTTP. This library does not host those services.

### Conversion pipeline

`text2fhir` and `voice2fhir` are explicit-adapter pipelines:

1. Minimize identifiers in the narrative (unless `DeidPolicy(mode=DeidMode.OFF)`).
2. Make **one** model call that extracts catalog-constrained entities. No model
   sees or emits a Bundle.
3. Restore minimized values only after the entity JSON is parsed.
4. Assemble typed FHIR deterministically (`assemble_bundle`).
5. Optionally bind exact terminology candidates (`bind_bundle`).
6. Run the validation cascade on the result.

Assembly refuses rather than approximates: `"62-year-old"` does not become a
`birthDate`, and `"128/82 mmHg"` does not become a `Quantity` of 128. Coded
concepts leave assembly as text; a separate binding stage adds a code only when
the caller's terminology adapter verifies a unique candidate.

The published extraction prompt in this package is the catalog and the general
contract. The production API composes an additional reviewed rule pack onto that
prompt; see
[`fhirbridge.llm.extraction_rules`](https://github.com/Safwanmahmoud/FHIR-It-Will/blob/main/src/fhirbridge/llm/extraction_rules.py)
in FHIR-It-Will.

## De-identify narrative

```python
from fhiratwill import DeclaredIdentifier, IdentifierClass, deidentify

result = deidentify(
    "Synthetic patient Ada Example has MRN TEST-123.",
    known_identifiers=[
        DeclaredIdentifier(IdentifierClass.NAME, "Ada Example"),
        DeclaredIdentifier(IdentifierClass.MRN, "TEST-123"),
    ],
)
safe_text = result.text
```

Enforced HIPAA Safe Harbor-style minimization is the default. Detection is deterministic,
known identifiers can be supplied by the caller, and the reversible in-memory vault is
cleared before the function returns. The output is still sensitive clinical data and this
feature does not by itself establish HIPAA or other regulatory compliance.

## Validate a FHIR resource

```python
from fhiratwill import validate

report = await validate(bundle)
```

Local mode runs structural and deterministic plausibility checks. It still returns all
eight layers: checks that require terminology or validator adapters are marked `skipped`,
source-evidence checks are `not_applicable`, and routing never claims automatic acceptance
while a required layer was skipped. Inject adapters for profile, terminology, and FHIRPath
validation; their outages propagate instead of becoming passes.

For the HTTP equivalent (`POST /v1/validate`) and the HL7 validator sidecar, use
[FHIR-It-Will](https://github.com/Safwanmahmoud/FHIR-It-Will#validate-a-resource).

## Convert text to FHIR

`text2fhir` accepts any implementation of the `LlmClient` protocol. Provider, model, key,
cost bound, and PHI acknowledgement are explicit request values; the library never reads
them from environment variables or HTTP headers.

```python
from decimal import Decimal

from pydantic import SecretStr

from fhiratwill import LlmInvocation, text2fhir

result = await text2fhir(
    "Synthetic patient reports a temperature of 38.2 C.",
    llm=my_llm_client,
    invocation=LlmInvocation(
        provider="local",
        model="reviewed-model",
        api_key=SecretStr("synthetic-key"),
        base_url="http://127.0.0.1:4000",
        max_cost_usd=Decimal("0.10"),
    ),
    seed="conversion-123",
    terminology=my_terminology_client,  # omit to return explicit unbound evidence
)
bundle = result.bundle
report = result.validation
```

The pipeline minimizes identifiers before model egress, validates the model's entity JSON
against a closed catalog, restores values only after extraction, assembles deterministically,
optionally verifies terminology, and runs validation. The result retains evidence for every
stage. An explicit `DeidPolicy(mode=DeidMode.OFF)` is required to disable minimization.

For the HTTP equivalent (`POST /v1/NAR2FHIR`) with BYOK headers and policy gates, use
[FHIR-It-Will](https://github.com/Safwanmahmoud/FHIR-It-Will#nar2fhir-convert-narrative-to-fhir).

## Convert voice to FHIR

```python
from fhiratwill import SpeechInvocation, voice2fhir

result = await voice2fhir(
    audio_bytes,
    media_type="audio/wav",
    speech=my_speech_client,
    speech_invocation=SpeechInvocation(
        provider="local",
        model="reviewed-stt-model",
        api_key=SecretStr("synthetic-key"),
        base_url="http://127.0.0.1:4000",
    ),
    llm=my_llm_client,
    llm_invocation=text_invocation,
    seed="conversion-124",
)
```

Audio is size-limited and external raw-audio egress is denied by default because audio
cannot be de-identified before transcription. External speech requires explicit permission
at both the high-level call and adapter policy. The transcript then follows the exact text
pipeline.

The optional LiteLLM adapter is imported explicitly:

```python
from fhiratwill.adapters.litellm import LiteLlmClient, LiteLlmPolicy

llm = LiteLlmClient(
    LiteLlmPolicy(
        local_only=False,
        egress_allowlist=frozenset({"api.openai.com"}),
    )
)
```

External invocations must also set `phi_egress_acknowledged=True`. Provider failures are
normalized into PHI-safe exceptions; prompts, transcripts, provider bodies, and keys are
never included in those exceptions.

For the HTTP equivalent (`POST /v1/VOICE2FHIR`) with `X-STT-*` headers, use
[FHIR-It-Will](https://github.com/Safwanmahmoud/FHIR-It-Will#voice2fhir-convert-dictated-audio-to-fhir).

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

This library stops at the plan. Submitting a transaction to an EHR is the
[production API](https://github.com/Safwanmahmoud/FHIR-It-Will#api-surface)
(`POST /v1/deliver`).

## Scope

This library:

- de-identifies narrative using deterministic, reviewed rules;
- validates FHIR locally and can orchestrate caller-provided validation adapters;
- converts text or transcribed audio through explicit model adapters;
- assembles grounded entity mappings into deterministic FHIR resources;
- verifies exact terminology candidates through a caller-provided adapter;
- checks and rebinds caller-supplied subject context; and
- compiles destination-neutral write plans.

This library does **not** expose HTTP endpoints, authenticate callers, persist
tenants, host a terminology or validator service, submit data to an EHR,
implement SMART authentication, guarantee that model output is clinically
correct, provide clinical decision support, or establish HIPAA, GDPR,
medical-device, or other regulatory compliance. Those production concerns are
the [FHIR-It-Will](https://github.com/Safwanmahmoud/FHIR-It-Will) service, which
depends on this package. Full profile, terminology, and invariant validation
still requires authoritative adapters and deployment-specific implementation
guides.

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
