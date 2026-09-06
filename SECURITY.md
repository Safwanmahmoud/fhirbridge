# Security Policy

## Supported versions

Security fixes are provided for the latest released minor version.

## Reporting

Report suspected vulnerabilities privately through GitHub Security Advisories:

https://github.com/Safwanmahmoud/fhirbridge/security/advisories/new

Do not include real patient data, credentials, or other secrets in a report. Use synthetic,
minimal reproductions. Please do not open a public issue for an unpatched vulnerability.

## Scope and safety

The base package performs no network I/O. Optional provider adapters can transmit clinical
text or audio only when the caller supplies credentials, acknowledges PHI egress, and
allowlists the destination. Applications remain responsible for transport security,
authorization, audit, deployment-specific FHIR validation, clinical review, and applicable
regulatory obligations.
