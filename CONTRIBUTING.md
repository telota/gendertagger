# Contributing

`AGENTS.md`, the normative documents in `docs/`, and accepted ADRs are the sources of truth. If
they disagree, stop and resolve the specification rather than choosing whichever behavior is easiest
to implement.

## Development setup

Install [uv](https://docs.astral.sh/uv/) at the version required by `pyproject.toml`, then run:

```bash
uv sync --locked
```

After the Git repository has been initialized, install the local hooks:

```bash
uv run --locked pre-commit install --install-hooks
```

The hooks format and lint changed files, validate documentation and contract naming, validate the lockfile and
repository metadata, run strict typing and import-boundary checks, and run the fast test suite before a push.
CI remains authoritative.

## Required checks

Run the same checks CI runs before opening a merge request:

```bash
uv lock --check
uv run --locked python scripts/check_documentation.py
uv run --locked python scripts/check_contract_naming.py
uv run --locked python scripts/check_package_initializers.py
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked lint-imports
uv audit --locked
uv run --locked pytest \
  -m "not integration and not postgres and not redis and not e2e and not slow and not gpu and not external" \
  --hypothesis-profile=ci --cov --cov-report=term-missing --cov-report=xml
uv build --no-sources
uv run --locked python scripts/check_distribution.py dist/*
```

Use `uv run --locked pre-commit run --all-files` to exercise all pre-commit-stage hooks manually.

## Change discipline

- Keep merge requests narrow and explain contract, persistence, provenance, scientific, security,
  and deployment effects.
- Add or update tests at the layer where behavior belongs. Do not hide a failed invariant behind an
  end-to-end test alone.
- Use Pydantic models at application boundaries. Never expose SQLAlchemy models through services or
  the public API.
- Treat OpenAPI changes as public contract changes and review generated diffs deliberately.
- Include a reviewed Alembic migration with every persistence change once Phase 2 begins.
- Record model, data, configuration, prompt, and method revisions that affect reproducibility.
- Use narrowly scoped, error-code-specific `# type: ignore[...]` and `# noqa: ...` comments with a
  reason. Broad suppressions and unchecked missing imports are not accepted.
- Follow the naming, Google-style docstring, Markdown, and ADR rules in
  `docs/19-coding-and-documentation-style.md`. Public contract field renames require explicit compatibility
  review.
- Keep production `__init__.py` files docstring-only. Import symbols from their defining modules and read the
  installed version through `importlib.metadata`.
- Keep ordinary tests deterministic and offline. Live services, model downloads, GPUs, and large
  corpora belong in explicitly marked protected/scheduled jobs.

## Scientific changes

Changes to labels, normalization, aggregation, authority overrides, tie behavior, certainty tiers,
TEI output semantics, or evaluation definitions must update the relevant design document, add an
ADR, and change explicit scientific regression expectations in the same merge request. Never update
golden outputs merely to make a failing test pass.

Keep two distinct regression oracles:

- `legacy_characterization` records what the old pipeline actually did;
- `reference_v1` records the approved normative behavior.

Any difference between them must be intentional and documented.

## Data and generated files

Only synthetic or explicitly cleared, licensed fixtures may enter Git. Never commit source editorial
data, databases, model weights, secrets, runtime artifacts, or anything under `__scrap/`. Raw source
fixtures whose byte hash is tested belong under `tests/fixtures/raw/`; expected scientific outputs
must not be regenerated during an ordinary test run.

See `docs/18-engineering-and-quality.md` for the full engineering policy and
`docs/19-coding-and-documentation-style.md` for naming and documentation conventions.
