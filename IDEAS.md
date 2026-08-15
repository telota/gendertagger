# Ideas

- Import registers from git url
- download tools for models/datasets for methods
- train classifier on gnd data, bracket by century -> use date of birth of person for that
- check for redundancies, backwards compatibility and legacy components
- add type stubs to deps

- extend cli

## Problem
- wikidata to strict normalization

unify handling of deps of methods -> why some extras?


## Improve test coverage
Yes—but coverage should increase around risk, not merely to inflate the percentage.

Current combined branch coverage is already **89.65%**, while the core scientific modules—normalization, reference aggregation, and certainty assessment—are at 100%. The remaining weak areas are mostly operational:

| Area | Coverage | Valuable additions |
|---|---:|---|
| `tasks/relay.py` | 69.29% | Coordinator startup, shutdown, signal handling, and failure loops |
| `api/run_events.py` | 65.67% | SSE reconnect, invalid event IDs, disconnects, and terminal transitions |
| `db/aggregation_repository.py` | 74.13% | Provenance drift, invalid ownership/status, and completeness failures |
| `api/aggregations.py` | 76.74% | 404/409/error mapping and dispatch rollback |
| `db/project_repository.py` | 78.49% | Invalid snapshot transitions, duplicates, and pagination boundaries |
| `storage/local.py` | 87.07% | Traversal protection, failed writes, missing artifacts, cleanup |

I recommend:

- Raise the combined project floor from **80% to 85% now**.
- Keep the fast-suite floor at 70% until more API/service tests land.
- Add per-file 100% requirements for normative scientific modules so global coverage cannot conceal regressions there.
- Target **90% combined coverage after Phase 5 is complete**, then ratchet the gate.
- Recalculate after merging HIVOTO because new production code changes the denominator.

I would next implement a focused test commit covering aggregation provenance/rollback, SSE behavior, relay lifecycle, and storage security. Those tests would improve confidence materially, not just the number.
