# ADR-0029: Unconditional classification method dependencies

**Status:** Accepted

## Context

Previous adapter decisions ([ADR-0012](ADR-0012-name-based-classifier-adapter-pattern.md),
[ADR-0013](ADR-0013-wiki-gendersort-adapter.md), [ADR-0019](ADR-0019-nomquamgender-adapter.md),
[ADR-0024](ADR-0024-hf-transformer-model-manifest-adapters.md),
[ADR-0025](ADR-0025-hivoto-xgboost-adapter.md), [ADR-0026](ADR-0026-local-llm-adapter.md)) declared
per-method runtime libraries (`gender-guesser`, `unidecode`, `nomquamgender`, `transformers`, `torch`,
`httpx2`, `xgboost`) as opt-in package extras under `[project.optional-dependencies]`.

In practice, the normative reference ensemble (`reference_v1`) requires all nine reference methods to
participate in the aggregation vote. Running the pipeline without installing all extras caused missing
methods to raise permanent `MethodDependencyError` exceptions and fail the aggregation run entirely.
Furthermore, containerized deployments (such as `deploy/docker/backend.Dockerfile`) and standard
`uv sync` or `pip install` workflows defaulted to an environment missing method libraries unless six
separate extras were explicitly requested.

## Decision

Move all classification method libraries from `[project.optional-dependencies]` into standard core
dependencies in `[project.dependencies]`:

- `gender-guesser>=0.4,<1`
- `httpx2>=2.0,<3`
- `nomquamgender>=0.1,<1`
- `torch>=2.2,<3`
- `transformers>=5.5,<6`
- `unidecode>=1.3,<2`
- `xgboost>=3.2,<4`

Remove `[project.optional-dependencies]` entirely from `pyproject.toml`.

Classification adapters continue to use lazy instantiation and cached backend factories so that
importing `gendertagger` and booting the FastAPI web application remain immediate without paying
heavy module import overheads (such as PyTorch) during application startup.

## Consequences

- Every installation of `gendertagger` (local environment, Celery workers, API server, and Docker
  containers) has complete out-of-the-box support for all reference and experimental classification
  methods.
- Eliminates configuration friction and environment divergence across local runs, CI pipelines, and
  container images.
- The `[project.optional-dependencies]` section is removed from `pyproject.toml`, simplifying
  dependency management.
- `MethodDependencyError` remains in `gendertagger.methods.base` to represent missing or unprovisioned
  compiled lookup artifacts and model manifest files at runtime.
