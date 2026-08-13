# ADR-0005: Local/private processing is the default

**Status:** Accepted

## Context

Editorial register data may be restricted and the reference study executes locally, including the LLM. GND is resolved from a local snapshot.

## Decision

The default deployment must support end-to-end local processing. External services are opt-in method adapters with explicit data-egress semantics.

## Consequences

- model/data artifacts must be versioned locally
- external service availability is not required for the reference pipeline
- deployments can satisfy restrictive archival/editorial environments
