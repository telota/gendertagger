# Coding, naming, and documentation style

## Purpose

Names and documentation are part of the system contract. They must preserve scientific distinctions,
make public boundaries understandable without reading their implementation, and remain cheap to check.
This policy complements the automated controls in the
[engineering and quality policy](18-engineering-and-quality.md).

Technical documentation, code identifiers, review notes, and diagnostics are written in English. Preserve
original-language source text, quoted labels, and standards terminology when translation would change their
meaning.

## Python naming

Follow these baseline forms:

| Construct | Form | Example |
|---|---|---|
| package or module | `snake_case` | `review_state.py` |
| function, parameter, or local value | `snake_case` | `resolve_final_label` |
| class, protocol, or exception | `PascalCase` | `DatasetSnapshot`, `SnapshotImportError` |
| module constant | `UPPER_SNAKE_CASE` | `DEFAULT_BATCH_SIZE` |
| serialized enum value | lowercase `snake_case` | `completed_with_errors` |

Acronyms behave as words inside identifiers: prefer `api_client`, `ApiClient`, `tei_parser`, and `TeiParser`.
Library-defined type names such as `UUID` retain their library spelling.

Names should reveal their domain role:

- functions use verb phrases; services, models, and values use domain nouns;
- collections are plural and counts end in `_count`;
- booleans should read as predicates such as `is_ready`, `has_more`, or `can_retry`; configuration flags
  may use a qualified `_enabled` suffix;
- avoid catch-all modules such as `utils.py` and vague names such as `data`, `info`, or `thing` when a
  stable domain term exists;
- tests use `test_<behavior>_<condition>_<outcome>` when that structure makes the expected behavior clearer.

Ruff's naming and built-in-shadowing rules enforce the mechanical baseline. Reviewers should still reject
grammatically valid names that conceal the domain concept.

## Package initializers

Use regular packages with an explicit `__init__.py`, but keep every production initializer inert. It contains
exactly one module docstring and nothing else. Imports, re-exports, `__all__`, version constants, functions,
classes, `TYPE_CHECKING` blocks, and runtime setup are forbidden.

Import a symbol from the module that defines it; do not create package-level shortcut APIs. Read installed
distribution metadata with `importlib.metadata`, for example `version("gendertagger")`, rather than maintaining
a second `__version__` value inside the package. This keeps dependency edges visible and prevents package
imports from triggering work or cycles.

## Contract-field vocabulary

Public Pydantic/JSON fields use `snake_case`. Renaming a serialized field is a public contract change and
requires an explicit compatibility decision, OpenAPI review, and contract-test update.

Use these domain conventions consistently:

- canonical classification output is `label`; an adapter's unnormalized value is `raw_label`;
- use `method_confidence`, `agreement_score`, or `certainty_tier`, never the ambiguous bare `confidence`;
- preserve `unknown`, `abstain`, and `error` as distinct names and concepts;
- use `tei_id` for TEI `xml:id`; qualify other authorities, for example `gnd_id`;
- resource identifiers are `id` on the resource itself or end in `_id`; UUID collections end in `_ids`;
- timestamp instants end in `_at`, for example `created_at`; calendar values end in `_date`;
- counts end in `_count`, and numeric durations state their unit, for example `timeout_seconds` or
  `poll_interval_milliseconds`.

The contract-naming validator inspects annotated class fields under `gendertagger.models` and
`gendertagger.config`. It deliberately does not ban legitimate terms such as `gender`, `snapshot_id`, or
short local loop names.

## Type hints, comments, and docstrings

Production modules and public classes, protocols, functions, and services require Google-style docstrings.
Tests normally rely on descriptive test names; add a test docstring when the rationale cannot be expressed
clearly in the name.

Docstrings explain the contract rather than restating type hints. Include the relevant details when they
exist:

- invariants, preconditions, and postconditions;
- observable side effects and transaction ownership;
- failure or retry behavior;
- units, ranges, nullability, and provenance semantics;
- the strategy/version and governing design document or ADR for normative scientific behavior.

Pydantic `Field(description=...)` text describes non-obvious serialized semantics for OpenAPI consumers.
Comments explain why a constraint or unusual implementation exists; do not narrate the following line.

Suppressions are narrow, name the exact Ruff rule or mypy error code, and include a reason. Generated code
may use a path-specific exclusion, but generated files must be clearly identified and reproducible.

## Markdown documents

Maintained project documentation consists of the top-level contributor/specification files, all Markdown
below `docs/`, and `frontend/README.md`. Each maintained document has:

- exactly one H1 as its first content line;
- optional closed YAML front matter may precede the H1 in non-ADR documents and is treated as metadata
  rather than document content;
- headings that descend one level at a time;
- balanced fenced code blocks with a language identifier where one is meaningful;
- portable relative links for repository content and HTTPS links for external content.

Wrap prose near 100 characters where practical for reviewable diffs. Tables, long identifiers, URLs, code,
and scientifically significant source text may exceed that target; line length is therefore advisory for
Markdown rather than an automated gate.

Numbered design documents use `NN-kebab-case.md`, retain stable numbers with gaps permitted after deletion,
and are linked from `00-design-index.md`. The filesystem is the authoritative document inventory; the
documentation validator discovers numbered design documents and ADRs directly. ADR numbers remain
contiguous because they are an immutable decision sequence.

## Architecture Decision Records

ADRs are immutable decision history. Create a new numbered record from the
[ADR template](decisions/TEMPLATE.md); do not rewrite an accepted decision to describe a different choice.
Use `Proposed`, `Accepted`, `Superseded`, or `Deprecated` as the status and include `Context`, `Decision`,
and `Consequences` sections in that order. A superseding ADR links to the earlier record and explains the
transition.

Scientific changes listed in `AGENTS.md` require both the governing design-document update and a new ADR in
the same merge request.

## Automated validation

Run the policy gates directly with:

```bash
uv run --locked ruff check .
uv run --locked python scripts/check_contract_naming.py
uv run --locked python scripts/check_package_initializers.py
uv run --locked python scripts/check_documentation.py
uv run --locked python scripts/check_dead_code.py
```

The documentation validator checks structure, local link targets, numbered-document/index coverage, and ADR
shape without accessing the network. The naming validator emits stable `GTN` rule
codes for the additional contract vocabulary rules. The initializer validator enforces regular package
markers without hidden imports or behavior. The dead-code validator enforces clean symbol definitions without
unreferenced functions or broken protocols. All four run in pre-commit and GitLab CI.
