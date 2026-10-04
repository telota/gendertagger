# Release gaps and remediation plan

Publication-readiness review dated **2026-10-03**. This record covers the software, repository contents,
operational documentation, and accompanying manuscript. It records findings, proposed fixes, and the
evidence needed to close each gap.

The initial review examined a changing working tree. The source/documentation recheck for this record used
HEAD `c9e3953ca97b8208de386ea3f7ac1042cb3779c1` plus local changes. Test and infrastructure work continued
concurrently. The verification results below describe their tested snapshots, not a successful release
pipeline for that commit. Revalidate every open item against the eventual publication commit.

P1 items should be resolved before publication. P2 items require a fix or an explicit, justified release
scope/limitation decision. P3 items are lower-priority usability corrections. **Open** means the reviewed
behavior remains present; **decision needed** means approval/provenance evidence was not found in the
reviewed records; **release task** means work needed to establish publication readiness.

## Gap register

| ID | Priority | Finding | Status |
|---|---|---|---|
| RG-01 | P1 | Password changes can overwrite administrative resets | Fixed; PostgreSQL regression coverage added |
| RG-02 | P1 | Private frontend caches survive account replacement | Fixed; account-isolation regression coverage added |
| RG-03 | P1 | Research data and personal metadata need publication clearance | Decision needed |
| RG-04 | P1 | Wiki-Gendersort publication rights and replacement provenance | Replacement verified; history/data decisions remain |
| RG-05 | P1 | HIVOTO-trained model lacks an explicit redistribution/licensing decision | Decision needed |
| RG-06 | P1 | Manuscript reports the wrong NQG threshold | Open |
| RG-07 | P2 | Method reference contradicts implemented contracts | Fixed; GND entity-type precedence restored |
| RG-08 | P2 | Project workers accept outputs under stale execution provenance | Fixed; compatibility and actual-worker receipts enforced |
| RG-09 | P2 | Technical classification errors remain cached after recovery | Fixed; technical errors excluded and cache evidence isolated |
| RG-10 | P2 | CSV analysis exports preserve spreadsheet-active values | Fixed; protected text encoding and supported Calc import verified |
| RG-11 | P2 | Quickstart omits required team bootstrap and roster membership | Open |
| RG-12 | P2 | Artifact detail screens do not validate route ownership | Fixed; canonical ownership and stale-navigation regressions verified |
| RG-13 | P2 | Delivery documents overstate release and migration verification | Corrected; manual process and local fresh-install/restore evidence recorded |
| RG-14 | P3 | Progress counts remain zero until an entire method completes | Fixed; intermediate/concurrent progress and GET/SSE verified |
| RG-15 | P2 | Human-override exports lack exact annotation-input provenance | Known open limitation |
| RG-16 | P2 | Publication version, immutable citation, and retained artifacts are unset | Release task |
| RG-17 | P1 | Final publication commit needs one complete verification record | Release task |

## Findings and fix plans

### RG-01: Serialize credential changes with administrative resets

**Evidence.** [AuthenticationService.change_password](backend/src/gendertagger/services/authentication.py)
reads and verifies the credential before writing, without a lock or revision check spanning those steps.
A real PostgreSQL/Argon2 reproduction paused verification, completed an administrative reset, and resumed
the password change. The stale request replaced the reset password and cleared `must_change_password`;
the administrator's returned temporary password was then invalid.

**Plan.** Use a consistent account/credential lock order or a credential-revision comparison across
password verification and replacement. Apply the same concurrency discipline to the administrative reset
and CLI paths. Verify the credential and account state after acquiring the protection; an unconditional
write after verification against stale state is insufficient. Keep API responses secret-free and document
the stale-operation response in [the security specification](docs/13-auth-and-security.md).

**Closure.** Add a PostgreSQL race regression using independent sessions and deterministic barriers.
Verify both orderings of user change versus administrative reset, concurrent user changes, rollback, the
forced-change flag, and revoked sessions. The losing stale operation must not undo a completed reset.
Ordinary login after session revocation is allowed by the existing policy; an in-flight login versus
revocation alone is not treated here as a separate confirmed defect.

**Remediation (2026-10-04).** Own-password changes and both HTTP/CLI reset paths now lock the owning
account before rereading and locking its credential. Locking reads refresh previously loaded ORM state;
verification, password replacement, and forced-change state remain protected until transaction completion.
Self-service changes recheck that the account is active. A request using a password superseded by a
completed reset or change fails with the existing `400 invalid_current_password` response. Resets retain
atomic password replacement/session revocation and permit inactive targets without reactivation. The
[security specification](docs/13-auth-and-security.md) records these semantics.

[PostgreSQL regressions](backend/tests/services/test_authentication_postgres.py) use independent sessions,
explicit barriers, observed database lock waits, and production Argon2 hashing. They cover both race
orderings through administrative and direct/CLI services, concurrent own-password changes, reset rollback,
forced-change flags, session revocation/retention, account deactivation, and stale ORM state. Application
and HTTP regressions retain the existing secret-free response contract.

**Verification (2026-10-04).** The remediation working tree based on
`b7a5b17d973facde7d50ac9a7c33ef5508707c06` passed the locked Core (1,685), PostgreSQL (290), and Redis
(7) suites, including all ten new credential-concurrency cases. Combined coverage is 87.60%; normalization,
reference aggregation, certainty assessment, and TEI projection each retain 100% coverage. Lock consistency,
documentation, contract naming, package initializers, dead-code policy, Ruff formatting/lint, mypy,
Pyright, Import Linter, Python/Node dependency audits, Alembic upgrade/schema-drift checks, isolated package
build/distribution validation, and generated frontend contract drift checks passed. Python was 3.11.15;
the unchanged backend `uv.lock` SHA-256 is
`2a07ac7e58c912fa7d098923203c4fb1b5e799a1bd0ce5d4e998faefecf92124`.
The final publication-commit verification record remains RG-17.

### RG-02: Scope private browser state to the authenticated account

**Evidence.** [Export queries](frontend/src/features/export/useExports.ts) and
[evaluation queries](frontend/src/features/evaluation/useEvaluations.ts) key private resources/artifacts
by resource ID without principal identity; artifact queries use `staleTime: Infinity`. During account
replacement through authentication recovery, the mounted screen can remain enabled. A mounted-app test
retained account A's private manifest after switching to B, issued no export read under B, and would have
received a denial had it queried the server.

**Plan.** Include principal identity in private collection, detail, and artifact query keys. Cancel or
ignore late responses belonging to a previous principal, remove private caches on replacement/logout,
and clear local downloaded content/object URLs. Audit the shared recovery path and other private feature
queries for the same pattern. Preserve the public branding and anonymous-classification boundaries.

**Closure.** Test A-to-B replacement while the detail view remains mounted, logout, loss of project
access, delayed artifact responses, and recovery as the same account. B must never see A's cached
content; fetching B's content must require B's authorization. Verify export and evaluation screens.

**Remediation (2026-10-04).** Private export, evaluation, run, aggregation, review, game, method-roster,
and upload-limit reads now include principal identity in their cache keys. The application synchronously
cancels private queries and removes private query/mutation results on account replacement or logout.
Public branding and anonymous classification retain their separate state. Private reads wait for
authentication and forced-change checks; rendering resolves the current owner's exact cache key and
hides retained data on authorization denials. Downloads carry cancellation and ownership through blob
hashing; obsolete completions cannot display or save bytes. Downloaded content and checksum inputs
clear on ownership/resource changes and access loss, and object URLs are always revoked after saving.

Request recovery captures the account and local ownership revision for every private request, including
requests that cannot replay. Account replacement, logout, and A-to-B-to-A transitions prevent old
requests from opening recovery or replaying. A declined obsolete recovery cannot forget the new
session. Session initialization, login flags, logout, and password responses reject stale ownership;
run streams ignore obsolete callbacks, and multi-command run creation and bulk review cannot continue
under a replacement account. Credential fields clear on account replacement, and recovery passwords
clear on dialog close and successful sign-in. Same-account recovery preserves eligible requests,
drafts, and completed downloads. [The frontend specification](docs/17-frontend-integration.md#state-ownership) records the
ownership policy.

[Mounted artifact regressions](frontend/tests/features/private-artifact-state.spec.ts) exercise both
detail screens through allowed/denied account replacement, logout/relogin, access loss, delayed
artifacts/downloads/hashing, and same-account recovery. Focused cache, transport, session, review/game,
run-stream, and command-continuation tests cover the shared ownership boundaries with synthetic data.

**Verification (2026-10-04).** The remediation working tree based on
`59bee5ddb32391d13a15ba76b302f79a552fbd94` passed all 1,811 frontend tests across 93 files with
84.53% branch coverage. Frontend lint, formatting, source/test/tooling type checks, translation-key
consistency, generated OpenAPI transport drift, dependency audit, and production build passed under
Node 26.10.0. The unchanged frontend lockfile SHA-256 is
`d94f8d1d274c7c25404b66c409fd845f0e1655af90cea3b360caec127de40f5c`.

The locked backend Core (1,685), PostgreSQL (290), and Redis (7) suites also passed. Combined coverage
is 87.60%; normalization, reference aggregation, certainty assessment, and TEI projection each retain
100% coverage. Lock consistency, documentation, contract naming, package initializers, dead-code
policy, Ruff formatting/lint, mypy, Pyright, Import Linter, Python/Node dependency audits, Alembic
upgrade/schema-drift checks, and isolated package build/distribution validation passed. Backend
dependencies and scientific regression expectations are unchanged. The final publication-commit
verification record remains RG-17.

### RG-03: Establish publication clearance for repository data and history

**Evidence.** [Contributor policy](CONTRIBUTING.md#data-and-generated-files) excludes editorial source
data, databases, and runtime artifacts from Git. Tracked files include
[editorial CSV input](data/input/schleiermacher_persons.csv),
[LLM results with reasoning](data/results/llm_gender_results.csv), and
[annotation](data/output/annotations.db) / [ground-truth](data/output/ground_truth.db) SQLite databases.
Read-only inspection found 8,093 editorial persons, 51 human annotations with nonempty annotator names,
and five named leaderboard entries in the annotation database. Actual names are not reproduced here.

The [legacy fixture approval](backend/tests/fixtures/scientific/legacy_characterization.json) covers
only identifiers/method outputs and excludes names, notes, life dates, alternative names, and LLM
reasoning. That approval governs the fixture; its exclusions alone do not establish the legal status of
every source file. Broader publication clearance was not found in the reviewed records.

**Plan.** Inventory tracked source data, derived results, databases, model assets, and reachable Git
history. Record rights, provenance, intended audience, and any personal metadata for each publication
candidate. Obtain explicit clearance or exclude/rehome the material into an appropriately licensed
research archive. Keep synthetic fixtures and the approved regression excerpts available to software
tests. Agree on a history-remediation plan before any destructive Git operation.

**Closure.** A reviewed inventory identifies exactly what will be published and under which permissions.
Inspect the actual source archive and public history, as well as the Python distribution. Package
exclusion checks alone do not establish source-repository publication safety.

### RG-04: Resolve Wiki-Gendersort publication rights and replacement provenance

**Evidence.** At the reviewed baseline, [the adapter](backend/src/gendertagger/methods/adapters/wiki_gendersort.py)
and [ADR-0013](docs/decisions/ADR-0013-wiki-gendersort-adapter.md) described verbatim upstream logic.
The [upstream repository](https://github.com/nicolasberube/Wiki-Gendersort) and
[source](https://raw.githubusercontent.com/nicolasberube/Wiki-Gendersort/master/Wiki_Gendersort.py)
were inspected during the review; no visible redistribution license was found. No local permission
record or third-party notice was found, and the user reports that the original author cannot be reached.
This is an unresolved permission-provenance issue, not a legal determination.
[GitHub's licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
distinguishes public availability from a redistribution license.

**Implementation completed.** The user authorized the specification, compatible replacement, comparisons,
and optimization. [ADR-0045](docs/decisions/ADR-0045-wiki-gendersort-compatible-implementation.md) and
[the behavior specification and verification record](docs/29-wiki-gendersort-compatibility.md) document
separation of source examination from implementation. The specification author examined the old source;
the implementation agent reports no such access. This process is not itself a legal clearance.

Current runtime routines have been replaced and versioned as `wiki_gendersort_v2`, retaining
`wiki_gendersort_v1` normalization, candidate order and duplicates, native labels, matched-name evidence,
consensus, and immutable SQLite provisioning. All 8,277 complete study predictions, 90,000 generated
candidate lists, 450,000 resolutions, 200,000 synthetic SQLite assignments, and 10,000 synthetic
predictions match the frozen reference. The committed synthetic suite adds 113 compatibility/cache tests.
Bounded character reuse and distinct-token batch reuse preserve those outputs; paired local benchmarks
measured an 8.01x improvement in study batch lookup. The old oracle stays outside Git and packages.
Scientific attribution and changed implementation provenance remain documented.

**Remaining plan.** Review the actual publication scope for historical copied source and the separate
`NamesOut.txt` table and compiled derivatives. Preserve the development and comparison evidence. If any
upstream code remains in published material, establish the applicable grant and record scope, source
revision, attribution, and required notices with explicit third-party license coverage. Separate table
acquisition does not itself establish permission to use it.

If these questions remain unresolved, a reduced software release can omit uncleared material. Disabling
a method alone does not exclude its source from the Python distribution. The published `reference_v1`
aggregation requires Wiki-Gendersort, so omission cannot be presented as a complete reproduction of that
workflow. A reviewed current-source archive or a new public repository can exclude old copied source
without rewriting the working repository; assess the full artifact inventory before publication.

**Closure.** Replacement development provenance and equivalence evidence are recorded. Before declaring
the publication gap closed, the rights/scope decision must cover the actual shipped source, package,
history, and data. Existing scientific outputs stay frozen. Any later method or normalization semantics
change requires the governing design update, a new ADR, and explicit scientific regression review.

### RG-05: Decide the HIVOTO model's distribution and license

**Evidence.** [Model provenance](data/models/hivoto_xgboost/PROVENANCE.md) identifies HIVOTO as the
training source. [The source reference](docs/references/methods/hivoto.md) records CC BY-NC-SA 4.0.
[ADR-0025](docs/decisions/ADR-0025-hivoto-xgboost-adapter.md) explains why the project-trained model was
committed but does not record an explicit redistribution/license assessment for the artifact.

**Plan.** Record a reviewed decision covering source-data terms, model distribution, attribution, the
artifact's license, and intended publication use. Training a model does not by itself resolve those
questions. If needed, distribute the model separately or provide provisioning instructions while
excluding it from the software publication. Keep hashes and provenance for the chosen distribution.

**Closure.** The model's publication record states what may be redistributed, under which terms, and
with which attribution. The source archive, README license statement, and provisioning workflow agree
with that decision.

### RG-06: Correct the manuscript's NQG method description

**Evidence.** [The manuscript](docs/paper/article.tex), in the NQG method and reproducibility paragraphs,
states `p = 0.5`. The study's legacy implementation and
[current adapter](backend/src/gendertagger/methods/adapters/nomquamgender.py) use threshold `0.1`:
male at probability at most `0.1`, female at probability at least `0.9`, otherwise uncertain, followed
by the documented token-consensus/normalization behavior.
[ADR-0019](docs/decisions/ADR-0019-nomquamgender-adapter.md) explicitly identifies the earlier `0.5`
example as incorrect. The manuscript's confidence claim also needs to distinguish legacy per-token
probability evidence from current `method_confidence`.

**Plan.** Correct the manuscript to the behavior used for the study and clarify probability evidence.
Check the methods, reproducibility, limitations, reviewer-response material, and generated PDFs for the
same claims. Reconcile any uncertainty about the study run with preserved code/configuration/results.
Do not change scientific implementation or golden outputs to match the incorrect prose.

**Closure.** A reviewer can trace the described thresholds and evidence fields to the study artifacts
and accepted ADR. Rebuild and visually inspect the manuscript; retain approved scientific expectations.

### RG-07: Reconcile the method reference with canonical contracts

**Original evidence.** [The method reference](docs/20-method-adapters-reference.md) advertised a
nonexistent `GenderGuesserConfig.detector_type`, described first-token-only behavior, and mapped
`unknown` to abstention. [The adapter](backend/src/gendertagger/methods/adapters/gender_guesser.py)
accepts no such configuration parameter and classifies all tokens;
[normalization](backend/src/gendertagger/methods/normalization.py) preserves a successful substantive
`unknown`. The reference also omitted NQG's threshold configuration and promised HF softmax
`method_confidence` despite the implemented hard-label output contracts.

**Correction (2026-10-04).** Reviewed all ten entries against their Pydantic configuration,
descriptor, inputs, adapter/backend, normalization, evidence, artifact provenance, and governing
decisions. The reference now documents closed configuration examples, forenames-only input for
name-based methods, six shared priority reducers versus the experimental XGBoost reduction, native
Wiki labels and final no-name abstention, NQG's finite `(0, 0.5)` threshold/default `0.1`, HF argmax
outputs without confidence, and the local LLM's response, confidence, error, and routing boundaries.
The reference-only correction left scientific implementations, accepted ADRs, and golden regression
expectations unchanged.

**Verification.** All ten documented configuration examples validated against the registered
Pydantic models. Live gender-guesser and NQG runs confirmed multi-token, recognized-name,
unrecognized-name, and no-name outcomes. Probes verified the ten normalization profiles' distinct
unknown/abstain/error results and retained raw evidence, plus the LLM's batch-level confidence-range
failure for `1.1`.

The focused locked Core run below passed **476 tests**, including adapter conformance,
normalization, the paired scientific regressions, prediction/method contracts, and registry
validation:

```bash
uv run --locked python scripts/run_tests.py core -- \
  tests/methods tests/domain tests/contracts/test_method.py \
  tests/contracts/test_prediction.py tests/services/test_method_registry.py -q
```

Documentation, contract-naming, package-initializer, dead-code, Ruff format/lint, mypy, Pyright,
Import Linter, lockfile, package-build, and distribution checks passed. This is documentation-scoped
verification, not RG-17's fixed-revision release pipeline. PostgreSQL/Redis workflows, provisioned
HF-model inference, and a hosted LLM endpoint were not exercised.

**GND implementation correction (2026-10-04).** The user subsequently authorized correcting the
discovered conformance issue under
[ADR-0046](docs/decisions/ADR-0046-gnd-entity-type-precedence.md). Implementation `gnd_v2` now uses
recognized gender only for persons, preserves corporate-body institution classification, and emits
`Unbekannt`/`success + unknown` for every other entity type regardless of source gender. The
normalization profile, configuration, compiler/schema, immutable snapshots, and historical predictions
are unchanged.

The new compiled-snapshot regression failed before the fix on a male-coded family record. A runtime
smoke after the fix confirmed that male-coded place and female-coded family records become unknown
while retaining their gender evidence, snapshot bytes stay identical, and such records no longer
override a pooled female decision. Person and corporate-body authority overrides and missing-ID/row
abstention remain intact. This synthetic evidence does not establish affected production records.

**GND correction verification.** The compiled-snapshot regression now passes all **14** combinations
of recognized male/female gender with corporate bodies and the six other non-person entity families.
The complete Backend profiles passed: **1,699 Core**, **290 PostgreSQL**, and **7 Redis** tests,
including unchanged scientific golden expectations. Combined branch-inclusive coverage was
**87.76%**, exceeding the 85% floor; normalization, reference aggregation, certainty assessment, and
TEI projection each passed their 100% gates.

Documentation, lockfile, naming, package-initializer, dead-code, Ruff format/lint, mypy, Pyright,
Import Linter, package-build/distribution, and locked Python/npm dependency-audit checks passed.
Alembic upgrade-to-head and drift checks passed against a newly created temporary database, which
was removed afterward. This verifies the Backend correction in the changing workspace, not RG-17's
fixed-publication-revision pipeline; frontend and provisioned HF/LLM inference were not exercised.

### RG-08: Reject incompatible project workers before producing predictions

**Original evidence (2026-10-03).** [BatchExecutor](backend/src/gendertagger/services/execution.py) resolved the current
registry adapter and validated against its current descriptor, without comparing the persisted method
implementation/normalization versions or Run runtime identity. A focused probe accepted v2 output for
a persisted v1 execution. A deployment between acceptance and execution can therefore attribute new
outputs to old immutable metadata. Worker metadata also needs an actual execution identity.

**Plan.** Define the compatibility check in the provenance/task specifications. Compare persisted
method and runtime identity with the executing worker before prediction. Reuse the established public
classification provenance approach where appropriate. Record actual worker provenance through canonical
contracts; retain identifier-only task envelopes. Define recovery for incompatible queued work without
rewriting immutable predictions or silently replacing accepted provenance.

**Closure.** Test implementation, normalization, dependency/environment, source revision, and applicable
artifact/model drift. Compatible workers complete normally; incompatible workers produce no predictions
and a persisted, diagnosable outcome. Cover retry/duplicate delivery. Review migrations and regenerate
OpenAPI/frontend types if public contracts change.

**Status: Fixed (2026-10-04).** Compatibility, canonical worker receipts, unknown historical evidence,
and recovery are specified in
[ADR-0048](docs/decisions/ADR-0048-project-worker-provenance-compatibility.md) and the provenance/task
designs. Workers compare implementation/normalization, declared source/lock/image identity, actual
application/Python versions and installed dependencies, and the frozen config before adapter computation.
Pinned lookup/model pointers, types, checksums, byte sizes, manifest identity, registered members, and
materialized model files are verified. Mismatches persist `IncompatibleWorkerError` with no Predictions.

New Run `dependency_versions` is immutable acceptance-time evidence. TaskBatch `WorkerProvenance`
captures actual hostname/PID and environment plus declared build identity in the atomic claim; PostgreSQL
prevents receipt assignment before claim or rewriting afterward. Migration `20261004_0014` preserves
historical nulls without backfill and restores the previous guards on downgrade. Identifier-only task
envelopes remain unchanged; public Run schema and generated frontend types include the dependency map.
Legacy queued work without dependency evidence requires a newly accepted Run. Failed mismatched work
requires matching deployment and new acceptance, not reopening its terminal batch or changing its outputs.

**Evidence after remediation.** A real PostgreSQL service smoke completed a compatible batch with one
female result and one abstention. A source-identity mismatch failed permanently with zero new Predictions;
compatible redelivery retained the failed batch and original receipt byte-for-byte. The captured worker
reported Python `3.11.15`, application `0.0.0`, and 137 installed dependencies. Real Redis/Celery execution
persisted the actual receipt and matching dependency map. Regression coverage exercises all runtime and
method version boundaries, historical unknowns, frozen configuration, lookup/model byte drift, materialized
member drift, database bypasses, transient rollback, and duplicate delivery. Migration tests verify
upgrade/downgrade/re-upgrade while preserving historical resource payloads. Actual locked Alembic
upgrade-to-head and schema-drift checks passed on an owned temporary database, removed afterward.
Out-of-band LLM aliases remain operator-declared; this does not attest remote weights or reproduce
provisioned HF/LLM inference.

### RG-09: Prevent technical error results from poisoning classification caches

**Original evidence (2026-10-03).** [DirectClassificationService](backend/src/gendertagger/services/classification.py) cached
all predictions, including technical errors, without expiry. A fail-once adapter returned an error for
the same name twice with one adapter call; another name succeeded after recovery. Cached failures can
affect both direct requests and public jobs using this service.

**Plan.** Exclude technical errors from the result cache, or define a short bounded error lifetime with
an injected clock. Keep cache identity consistent with the method/configuration/artifact revisions that
determine output. Preserve the normal distinction between a substantive unknown and an execution error.

**Closure.** A transient failure followed by recovery retries the same name and returns fresh output.
Successful cache hits remain effective, and concurrent calls/eviction do not corrupt results. Do not
mutate previously persisted immutable job outputs as part of cache recovery.

**Status: Fixed (2026-10-04).** Technical errors, including synthesized raised/boundary failures, never
enter the bounded process-local cache or evict successful evidence. Identity uses method name, the
canonical complete descriptor/resolved-configuration digest, and exact name; default-equivalent
configurations share entries, while method/model/artifact changes do not. Successful substantive unknowns
and normal abstentions remain cacheable. Deep copies isolate stored and returned nested evidence.
No error expiry, automatic retry, durable cross-run cache, or completed-job rewrite was introduced.

**Evidence after remediation.** A fail-once wrapper around the installed GenderGuesser adapter processed
`Maria` three times with `error`, `success`, `success`, two adapter calls, and the recovered `female`
label. Direct-service regressions cover returned/raised/boundary errors, mixed batches, nested mutations,
LRU/disabled-cache behavior, canonical identity, pinned/latest/missing artifacts, and a deterministic
late-error race. Public-job regressions prove a fresh job recovers while the earlier errored job and its
completed outputs remain byte-for-byte unchanged on redelivery. The cache policy is documented in the
API and persistence designs.

### RG-10: Make analysis downloads safe for spreadsheet use

**Original evidence (2026-10-03).** The JSON/tabular path accepted identifiers such as `=1+1`;
[the CSV serializer](backend/src/gendertagger/export/csv_analysis.py) emitted them verbatim. CSV quoting
does not prevent spreadsheet applications from interpreting such cells as formulas. Other exported
free-text fields need the same review.

**Plan.** Define a spreadsheet-safe encoding policy or an explicit safe spreadsheet export. Cover
formula-leading characters and relevant whitespace/control prefixes in exported text. Preserve the
canonical identifier and raw source data in storage and a lossless machine-readable format. Document
the compatibility/round-trip consequences before changing export encoding; update the governing export
design and add an ADR where scientific/output semantics change.

**Closure.** Regression cases cover `=`, `+`, `-`, `@`, prefix variations, and normal text. Opening the
intended analysis download in supported spreadsheet tools treats those values as text. JSON/canonical
identifiers and existing stored artifacts remain unchanged.

**Status: Fixed (2026-10-04).**
[ADR-0047](docs/decisions/ADR-0047-spreadsheet-safe-csv-analysis.md) and
[the export policy](docs/08-ingestion-and-export.md#spreadsheet-safe-csv-analysis) define quoting every
cell and prefixing hazardous text with exactly one ASCII apostrophe. ASCII/full-width `=`, `+`, `-`,
`@`, Unicode whitespace, and Cc/Cf control/format prefixes are covered without removing source text.
Canonical IDs/records, JSON, TEI, completed export bytes, and existing manifests are not rewritten.

**Evidence after remediation.** Valid canonical regression records cover both arbitrary-text columns
(`tei_id`, `resp`), ordinary text, absent values, quoting/newlines, original apostrophes, and unchanged
JSON. A real PostgreSQL/storage/download regression verifies old CSV/manifest downloads remain unchanged
while new CSV is protected and new JSON retains exact identifiers, with matching persisted sizes/hashes
and duplicate-safe export execution. An isolated LibreOffice Calc `26.8.0.3 680(Build:3)` headless
text import of actual serializer bytes produced 264 string cells and zero formula cells. The exact
supported filter and reproduction recipe are recorded in the export design; its temporary CSV/XLSX and
office profile were removed.

The supported workflow is explicit Calc Text CSV import with UTF-8, comma only, double-quote delimiter,
quoted fields as text, every column Text, and formula evaluation/trimming/delimiter merging disabled.
Protective apostrophes may remain visible. Calc newline normalization and XLSX control escapes mean this
is text/non-formula proof, not a lossless spreadsheet round trip or graphical-display proof. Excel,
arbitrary import defaults, copying into formula contexts, and CSV save/reopen are not safety guarantees;
JSON/source artifacts remain the canonical round-trip formats.

### RG-11: Add team bootstrap to the quickstart

**Evidence.** [The quickstart](QUICKSTART.md#6-add-accounts-and-method-data-as-needed) creates a reviewer
and immediately grants a project role. [Membership administration](backend/src/gendertagger/services/project_access.py)
requires active direct membership in the project's team first. Initial
[project creation](backend/src/gendertagger/services/projects.py) also requires a team and eligible
manager. The guide supplies neither team bootstrap nor roster prerequisites.
The [reviewer responses](docs/paper/response-to-reviewers.tex) promise sample data, while
[the reviewer checklist](docs/paper/reviewer-checklist.md) still leaves runnable setup, dummy input,
and reproducible installation evidence open.

**Plan.** Document team creation, the initial manager's roster membership, first-project creation,
and adding a reviewer to that same team before granting a project role. Use existing UI/CLI contracts
and explain team eligibility separately from project data access. Keep local and server instructions
consistent. Ship a small synthetic or explicitly cleared, importable example dataset and link it from
the guide with concrete upload/run/review instructions. The development seeding script is not a
substitute for a reader-facing import example.

**Closure.** Follow the guide from a fresh database through administrator setup, team/project creation,
reviewer membership, and a small synthetic import/review. Verify CLI commands and equivalent UI steps.
Use the shipped example and reconcile the reviewer-response/checklist status with the recorded results.
The two related CLI test failures from the initial review have changed fixtures; track their recheck
under RG-17 rather than assuming they remain failures.

### RG-12: Validate detail-resource ownership against route context

**Original evidence (2026-10-03).** [ExportDetailView](frontend/src/features/export/ExportDetailView.vue)
fetched an export without validating its relationship to route project/run IDs, then built aggregation
links from those IDs. A reproduction opened an export beneath an unrelated project/run and produced
the wrong link. [EvaluationDetailView](frontend/src/features/evaluation/EvaluationDetailView.vue) and
[AggregationDetailView](frontend/src/features/runs/AggregationDetailView.vue) had equivalent gaps.
Server authorization still applies; this finding concerns inconsistent client context, not a confirmed
server authorization bypass.

**Plan.** Resolve and validate resource-to-run-to-snapshot-to-project ownership using canonical API
responses before rendering detail content or links. Prefer an existing shared route-context pattern.
Fail closed for mismatches and stale navigation; keep business rules in the API rather than introducing
page-specific backend endpoints.

**Closure.** Test mismatched project/run/resource IDs, direct refreshes, rapid route changes, and correct
deep links for all three screens. No artifact or evidence is presented under an unrelated context.

**Remediation (2026-10-04).** All three screens share
[`useArtifactRouteContext`](frontend/src/composables/useArtifactRouteContext.ts), reusing the existing
project/run/snapshot queries to validate canonical ownership before exposing detail data. Manifest/report
reads and export download/hash continuations require that valid context. Principal and complete-route
changes invalidate pending download ownership, including navigation away and back. Mounted regressions
cover mismatched IDs at every link in the chain, delayed reads, deep links, and stale downloads; real
Chromium verified correct links, rejection states, and cancellation of an obsolete HTTP download.

### RG-13: Align delivery claims with implemented and verified operations

**Original evidence (2026-10-03).** [The implementation plan](docs/15-implementation-plan.md#phase-7-deployment-hardening)
marked protected tagged publication and previous-release migration rehearsal complete.
[Engineering policy](docs/18-engineering-and-quality.md) and
[the production runbook](docs/21-production-promotion.md) instead described commit-based publication,
deferred versioned-release automation, and a helper that established neither a previous schema nor the
readiness endpoint it probed. [The frontend overview](frontend/README.md) also understated delivered
screens.

**Plan.** Distinguish implemented capability, completed verification, and deferred automation. Correct
the roadmap/overviews immediately. Choose a documented manual or automated release process for the
publication scope. Before claiming upgrade readiness, rehearse target migrations against an isolated
copy of the actual previous schema/data and verify startup, restore, and rollback. Retire the
misleading `deploy/scripts/test_migration.sh` helper rather than treating it as upgrade evidence.

**Closure.** Documentation agrees with CI and operational commands. A retained rehearsal record names
previous/target versions, images, database state, backup/restore checks, and smoke-test results. Where no
previous release exists, record fresh-install evidence and the upgrade limitation explicitly.

**Remediation (2026-10-04).** Plans, overviews, and operational guidance now distinguish implementation,
completed checks, and deferred automation. Manual digest-based promotion remains the publication
process; the misleading migration helper is removed. The
[local fresh-install/restore record](#rg-13-local-fresh-install-and-restore-evidence-2026-10-04)
names the tested source/environment, service digests, database baseline, backup checksums, restored data,
and startup results. No previous tagged release is defined, and existing-installation upgrade,
previous-image rollback, and published-image promotion are explicitly unverified operator gates.

### RG-14: Refresh progress after every terminal batch

**Original evidence (2026-10-03).** [Execution finalization](backend/src/gendertagger/db/repositories/run_repository.py)
returned while any batch was outstanding before refreshing execution tallies. With one completed
200-record batch and another pending batch in a 400-record execution, progress stayed zero. Run GET and
SSE inherited those counts.

**Plan.** Refresh tallies independently of the terminal-state decision, under the existing concurrency
protection, and aggregate run progress consistently. Preserve definitions of completed/failed counts
and the separation between success, abstention, and technical errors.

**Closure.** Multi-batch and concurrent-worker tests show accurate intermediate counts, identical
GET/SSE state, no duplicate counting, and unchanged final lifecycle transitions.

**Remediation (2026-10-04).** Every terminal batch refreshes execution tallies before the terminal-state
decision. Serialized `FOR NO KEY UPDATE` finalization avoids conflicts with Prediction foreign-key
locks, and refreshed ORM state observes competing workers' commits. Regressions cover concurrent
completion with/without outstanding work, cached parent/child rows, duplicate deliveries, partial/all
batch failures, outcome distinctions, and GET/SSE equality. An actual 400-record run reported
`200 completed / 0 failed / 50%` while still running; redelivery left 200 Predictions and counts unchanged,
and its final batch reached `400 / 0 / 100%` with the normal completed lifecycle.

### RG-15: Persist the review inputs used by human-override exports

**Evidence.** [The v1 manifest](backend/src/gendertagger/models/export.py) records label policy but
not the exact annotation heads/revisions used. Later reviews prevent exact reconstruction of those
inputs. [The aggregation workflow plan](docs/28-aggregation-workflow-plan.md#5-make-reviewed-exports-the-default)
already acknowledges and proposes addressing this limitation. It is not a newly discovered design
discrepancy, and retained export output bytes remain available.

**Plan.** Implement the planned versioned review-input provenance before claiming fully reproducible
human-override exports or expanding their default use. Capture one consistent worker-time selection
including annotation IDs/revisions, no-head records, and deferred heads. Render labels and provenance
from that same selection; reference a checksummed review-input artifact in manifest v2 and retain human
responsibility configuration. Preserve v1 readers and artifacts, append-only annotations, and existing
label resolution. Keep large selections out of task messages. Update design/ADR/contracts first.

**Closure.** An export is reproducible after subsequent annotations, and concurrent review cannot create
a mixed input selection. Retries reuse any durably captured selection; a wholly rolled-back attempt
does not count as captured. Test machine-only exports and v1 compatibility. If deferred, disclose the
exact limitation in release/manuscript claims and record the release-scope decision.

### RG-16: Establish immutable publication identity and artifacts

**Evidence.** [Backend metadata](backend/pyproject.toml) still uses version `0.0.0`;
[CITATION.cff](CITATION.cff) has no release version/date or immutable archive identifier. The manuscript's
[software citation](docs/paper/gendertagger.bib) points to the moving repository. These are release
preparation tasks rather than runtime defects.

**Plan.** Select the publication scope, version, and exact commit after fixes. Synchronize package and
citation metadata and update the software citation to an immutable version/archive where available.
Make these metadata changes before final release verification so the tested commit is the published one.
Publish only cleared source/data/model material. Retain package/source checksums, image digests, SBOMs,
the matching lockfile, environment/provenance records, and deployment instructions beyond CI's artifact
expiry. Select the archival destination and final publication date deliberately; do not invent a DOI.

**Closure.** A reader can retrieve the cited version, verify its artifacts, install it from a clean
checkout using documented instructions, and identify which data/models are required separately.

### RG-17: Run the complete release verification on one fixed revision

**Evidence.** The initial suites were broadly successful but included two PostgreSQL CLI test failures
and 15 Pyright diagnostics during concurrent test/CI edits. The CLI team fixtures and optional TypedDict
accesses have since been corrected in source. Targeted rechecks are recorded below; earlier failures
must not be described as current without rerunning them. Ongoing PostgreSQL isolation work is outside
the scope of this document-only change.

**Plan.** Promote the confirmed race/cache/provenance/CSV reproductions into maintained regressions
with the relevant fixes. Once the release tree is stable, run the complete locked backend/frontend
checks in [CONTRIBUTING.md](CONTRIBUTING.md#required-checks), including all canonical test profiles,
migrations/schema drift, combined coverage, scientific branch gates, dependency audits, contract drift,
package validation, and production build. Complete fresh-install/browser and operational verification.
Retain one record tied to the exact release commit; partial passing snapshots are not that record.

**Closure.** Every applicable gate passes for the publication revision, all P1 gaps are closed, and
remaining gaps have documented scope/limitation decisions. Evidence identifies commit, lock hashes,
tool versions, tested artifacts, and actual outcomes without embedding credentials or private data.

## Implementation sequence

| Step | Work | Dependencies and exit |
|---|---|---|
| 1 | Establish publication scope and rights inventory: RG-03, RG-04, RG-05 | Record decisions for every redistributed source/data/model asset; no history rewrite as an incidental cleanup |
| 2 | Completed: credential concurrency and private account state, RG-01/RG-02 | PostgreSQL and mounted-app regressions passed; API/session and principal boundaries preserved |
| 3 | RG-07 completed; manuscript threshold RG-06 remains open | Method prose follows accepted contracts; the manuscript still needs its separate correction |
| 4 | Completed: worker provenance and caches, RG-08/RG-09 | Compatibility/recovery specified first; mismatches write no predictions; recovered methods retry uncached errors |
| 5 | RG-10/RG-12 completed; annotation-input provenance RG-15 remains open | CSV policy, canonical route ownership, stale-navigation regressions, and real browser behavior verified |
| 6 | RG-13/RG-14 completed; setup RG-11 remains open | Documentation matches manual delivery and local fresh-install/restore evidence; intermediate progress is verified; deployed upgrade/rollback still requires operator rehearsal |
| 7 | Prepare publication version and citation metadata: RG-16 | Make metadata changes before freezing the release candidate |
| 8 | Stabilize the tree and run every gate: RG-17 | One complete passing verification record for the chosen commit |
| 9 | Publish and retain verified artifacts: RG-16 | Metadata matches the verified commit and published artifact digests; archive only cleared material |

Use separate, reviewable changes for these workstreams. Contracts and governing design decisions precede
implementation where needed. Update the relevant design document and add an ADR before changing labels,
normalization, aggregation, authority overrides, certainty tiers, TEI output semantics, or evaluation
definitions. Persistence changes require reviewed migrations. Public contract changes include reviewed
OpenAPI and generated frontend transport changes. No repair may overwrite immutable predictions/results,
mutate annotation history, or silently change the published reference behavior.

## Verification record

The following results come from the initial review on 2026-10-03; they are historical evidence, not a
claim that all checks passed together on the current HEAD and working tree.

| Check | Observed result |
|---|---|
| Backend lock, documentation, contract naming, package initializers, dead-code policy, Ruff | Passed at reviewed snapshots |
| Backend mypy and import boundaries | Passed at reviewed snapshots |
| Backend fast suite | 1,416 passed |
| Backend PostgreSQL suite | 269 passed; two CLI membership tests failed due to missing team eligibility in fixtures |
| Backend Redis/Celery suite | All seven passed using isolated PostgreSQL databases and dedicated Redis database 15 |
| Combined backend coverage | 87.42%; all four scientific coverage modules reached 100% including branches |
| Backend package build/distribution check | Wheel and source distribution passed |
| Python lockfile and backend/frontend npm dependency audits | No known vulnerabilities reported at the time of the audits |
| Frontend lint, formatting, typechecks, i18n, OpenAPI drift, production build | Passed |
| Latest frontend coverage run in initial review | 1,699 tests in 88 files passed; 84.28% branch coverage |
| Pyright during late initial-review edits | 15 optional TypedDict-access diagnostics in `test_verification_ci.py`; source subsequently changed |
| Focused authentication reproductions | Administrative-reset/password-change race confirmed with PostgreSQL and Argon2; temporary database cleaned up |
| Focused frontend reproduction | Account replacement retained private export manifest; mismatched route produced incorrect aggregation link |
| Focused method/execution/export reproductions | Stale adapter provenance, cached technical errors, spreadsheet-active CSV ID, and zero intermediate progress confirmed |

Temporary review probes were stored outside Git. Their behavior is described above so closure does not
depend on those ephemeral files; maintain regression tests with each implementation fix instead of
committing local scripts, credentials, private data, or runtime artifacts.

**Historical document-preparation recheck (2026-10-03):** both previously failing CLI tests passed
against isolated temporary PostgreSQL databases, and Pyright reported zero errors/warnings. Those
specific historical failures were resolved; this targeted recheck did not replace a full suite or verify
unrelated concurrent changes. Other findings were still open at that initial-review snapshot.
The gap register and individual remediation records above are authoritative for current status, including
the completed RG-01, RG-02, RG-07, RG-08 through RG-10, and RG-12 through RG-14 corrections. Rights findings still require decisions.

### RG-08 through RG-10 integrated verification (2026-10-04)

This verifies the changed working tree based on HEAD `0509115`, not a frozen publication revision.
The earlier RG-01/RG-02/RG-07 closures remain intact; unrelated publication, rights, manuscript,
navigation, and annotation-provenance findings retain their own statuses.

| Check | Observed result |
|---|---|
| Backend Core profile | 1,775 passed; final focused cache/CSV/export cases also passed |
| Backend PostgreSQL profile | Final complete run: 313 passed after correcting three new fixture setup failures |
| Backend Redis/Celery profile | All seven passed on dedicated Redis DB 15 and isolated PostgreSQL databases; final worker-receipt case also passed |
| Combined backend coverage | 87.83%; normalization, reference aggregation, certainty assessment, and TEI projection each reached 100% including branches |
| Backend policy/static gates | Locked environment, documentation, contract naming, package initializers, dead code, Ruff formatting/lint, mypy, Pyright, and all six Import Linter contracts passed |
| Migration proof | Actual locked Alembic upgrade-to-head/check passed; forward/downgrade/re-upgrade regression preserved historical payloads and enforced new receipt guards |
| Canonical transport contract | OpenAPI snapshot and frontend transport types regenerated; backend snapshot tests and frontend drift check passed |
| Backend package artifacts | Final wheel/source distribution built; distribution policy passed for both |
| Dependency audits | Locked Python audit: no known vulnerabilities/adverse statuses in 143 packages; backend/frontend npm audits: zero vulnerabilities |
| Frontend checks | Lint, formatting, typechecks, i18n, transport drift, and production build passed |
| Frontend covered suite | 1,811 passed in 93 files; 90.92% statement and 84.53% branch coverage |
| Runtime proof | Compatible worker completed; incompatible source wrote zero Predictions; terminal redelivery was unchanged; recovered real adapter returned fresh output; actual Calc import contained zero formulas |

Backend runtime: Python `3.11.15`, application `0.0.0`, pytest `9.1.1`, PostgreSQL `16.15`.
The unchanged locked environment digest was:

```text
backend/uv.lock SHA-256: 2a07ac7e58c912fa7d098923203c4fb1b5e799a1bd0ce5d4e998faefecf92124
```

Temporary worker-smoke databases and Calc CSV/XLSX/profile files were removed. No production database,
user office profile, source editorial data, provisioned HF/LLM inference, or graphical spreadsheet
surface was used for these checks. This record does not close RG-17 or claim release-artifact publication.

### RG-13 local fresh-install and restore evidence (2026-10-04)

This record covers locked source from HEAD `05091151bc6726cd3a1b49379c806fad3ec36126` plus the
release-gap working-tree changes. It is not a publication commit or a target-image promotion record.
`git tag --list` returned no tags; the package version is `0.0.0`. No previous tagged application
release or published previous/target image pair was identified, so upgrade and previous-image rollback
remain **unverified**. Manual digest-based promotion is the documented publication process; version-tag
automation remains deferred.

| Field | Observed evidence |
|---|---|
| Previous/target application | Previous release: none defined; target: local locked-source `0.0.0` working tree, not published application images |
| Source/environment identity | Backend lock SHA-256 `2a07ac7e58c912fa7d098923203c4fb1b5e799a1bd0ce5d4e998faefecf92124`; frontend lock SHA-256 `d94f8d1d274c7c25404b66c409fd845f0e1655af90cea3b360caec127de40f5c`; uv `0.12.21`, Node `26.10.0`, npm `12.2.0` |
| Isolated services | Fresh Compose project `gendertagger-rg13-smoke`; PostgreSQL `postgres@sha256:44c4ee9810eff91f7eab4d822642e01115b1a9eccce4bcbdde7604752d68eac6`; Redis `redis@sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2` |
| Database baseline/target | Empty new PostgreSQL volume, migrated by locked `alembic upgrade head` to `20261004_0014`; `alembic check` found no new upgrade operations |
| Representative data | Existing development seed invoked as `uv run --locked python -m scripts.seed_frontend_development --confirm-development-database`; two synthetic projects, completed evaluation/export, and lifecycle/error fixtures |
| Startup/workflow | Actual Uvicorn application startup; `/health` and `/ready` returned `OK` after artifact-root initialization; real Chromium login reached the authenticated client |
| Backup helpers | Actual `deploy/scripts/backup.sh` and `restore.sh` with the isolated Compose project and expected named-volume layout; generated source-smoke artifacts copied into that separate volume for helper verification |
| Backup identity | Database dump SHA-256 `b8343bbf852fe6f6788160e8eb8d6ec536ef36237457e4fd08e16c1cbc85fc0b`; artifact archive SHA-256 `93a7ac262040c8d04c300b745a29e69d0160a236a549e713c1e80e0f1fc6fb96` |
| Restore checks | API stopped before restore; post-backup project-description mutation reverted, both projects and `20261004_0014` restored, and a post-backup artifact marker removed; all three original artifact SHA-256 values matched |
| Restored startup | The same locked-source application restarted successfully; `/health` and `/ready` again returned `OK` |
| Limits | No existing deployment/schema/data or production services changed; no prior-image rollback, published target-image startup, gateway/worker/coordinator promotion, or production acceptance was exercised |

The direct-file seed invocation first failed because repository-only `tests` imports were not on its
module path; the module invocation above supplied that context. Readiness initially returned
`503 Artifact storage unavailable` before the seed initialized storage; after initialization it returned
`OK`. These prerequisite failures are retained rather than counted as an uninterrupted install.
This local record closes inaccurate capability/verification claims, not RG-16 or RG-17.

### RG-12 and RG-14 integrated verification (2026-10-04)

This verifies the release-gap working tree based on HEAD
`05091151bc6726cd3a1b49379c806fad3ec36126`, not a frozen publication revision. Lock hashes and the
isolated runtime are recorded in the RG-13 section above. No schema or public API shape changed for
these fixes; OpenAPI and generated frontend types remain consistent without regeneration.

| Check | Observed result |
|---|---|
| Backend Core profile | 1,775 passed |
| Backend PostgreSQL profile | Final complete run: 323 passed, including concurrent workers, lifecycle/failure cases, cached ORM state, and intermediate GET/SSE equality |
| Backend Redis/Celery profile | All seven passed using isolated PostgreSQL databases and dedicated Redis DB 15 |
| Combined backend coverage | 87.85%; normalization, reference aggregation, certainty assessment, and TEI projection each reached 100% including branches |
| Backend policy/static gates | Lockfile, documentation, contract naming, package initializers, dead code, Ruff formatting/lint, mypy, Pyright, and all six Import Linter contracts passed |
| Backend package artifacts | Wheel/source distribution built; distribution policy passed for both |
| Dependency audits | Locked Python audit reported no known vulnerabilities/adverse statuses in 143 packages; backend/frontend npm audits reported zero vulnerabilities |
| Frontend static/build gates | Lint, formatting, typechecks, i18n, transport drift, and production build passed |
| Frontend covered suite | 1,844 passed in 93 files; 91% statement and 84.76% branch coverage |
| Actual artifact UI | Fresh valid export/evaluation/aggregation links resolved canonical ownership and produced correct detail links; wrong project or run hid content/status/evidence/actions and all main-content links |
| Download ownership | A real export download delayed at the browser transport was cancelled with `net::ERR_ABORTED` on project change; no stale links/checksum controls appeared. A later valid response produced the manifest-matching SHA-256 and 2,323-byte size |
| Visual scope | Real Chromium desktop/narrow captures; valid and rejected export states and rejected aggregation state remained usable; the valid 390px surface had no page-level horizontal overflow. Mechanical detector reported no findings |
| Actual progress path | Real authenticated TEI import of 400 records, API scheduling, and actual Celery task entry points: first 200-record batch gave running `200/400`, zero failed, 50% in GET, SSE, and the native UI progress element |
| Idempotency/completion | Repeating batch zero preserved counts and exactly 100 success + 100 abstain Predictions; batch one reached completed `400/400`, zero failed, 100%, with exactly 200 success + 200 abstain Predictions |

The first frontend run exposed an evaluation fixture missing canonical snapshot ownership data; the
first backend pass exposed a new API test using a nonexistent repository selector. Both fixture errors
were corrected before the final passing suites. Formatting and a dynamic-delete lint error were also
corrected. Failed passes are not release evidence.

The local API/Vite processes, isolated Compose project/volumes, synthetic artifacts/backups, and
throwaway task smoke were removed after verification. No existing development or production database
was modified. This closes RG-12/RG-14 correctness checks and RG-13's documentation correction, not
release-image publication, deployed upgrade/rollback readiness, full accessibility acceptance, or RG-17.



## Future improvement analysis: streamlined deployment and data/model provisioning

**Status:** Future improvement idea; current-state analysis dated **2026-10-03**. This is not an
approved implementation design, an additional release blocker, or a change to the priorities in the
gap register. The broader workflow needs a bounded design before implementation. Existing release
corrections remain tracked separately, particularly RG-11 for team bootstrap, RG-13 for operational
claims, and RG-03 through RG-05 for publication and redistribution decisions.

**Review scope:** Read-only inspection of source, configuration, documentation, existing tests, and
installed dependency code. No services were started, assets downloaded, provisioning executed, or
tests run for this analysis. These findings describe the repository, not a verified running instance.

### Improvement goal

Make the path from a fresh installation to a usable instance simpler, with fewer manual commands and
less knowledge of internal services or filesystem layouts. A future workflow should connect
installation, updates, data/model acquisition, validation, configuration, and readiness; explain
required and optional assets and their resource needs; and offer actionable diagnostics and safe
retries. Local/private operation, offline provisioning, checksums, version provenance, and licensing
requirements remain constraints.

### Current installation and update path

The repository already has a numbered [quickstart](QUICKSTART.md). Operators install Git, curl, and
Docker Compose, copy and protect `.env`, choose a database password, record the Git revision and
dependency-lock hash, and select a local or server Compose mode. They then build images, start
PostgreSQL and Redis, run migrations, create an administrator through a one-off API container, start
the remaining services, and inspect health and logs. A shared server additionally needs an independently
configured HTTPS proxy. Team/project bootstrap is incomplete in the guide, as recorded under RG-11.

Provisioning moves to [the README's method-data instructions](README.md#method-data). Updates and
rollback move to [the production runbook](docs/21-production-promotion.md); the local-image update path
is a shorter quickstart paragraph. There is a usable installation guide for an experienced Docker
operator, but no single guided workflow covering the complete instance lifecycle.

### Method and asset inventory

| Method | Separately provisioned requirement | Current provisioning route |
|---|---|---|
| `parenthetical_qualifier` | None | Built-in rules |
| `gender_guesser`, `nomquamgender` | None; reference data ships with the installed packages | Available after installation |
| `gnd` | Dated GND person and corporate-body MARC21-XML dumps from one release | `assets build-gnd` or checksum-pinned `assets fetch-gnd` |
| `wiki_gendersort` | Wiki-Gendersort `NamesOut.txt` | `assets prepare-wiki` or checksum-pinned `assets fetch-wiki` |
| `hivoto` | Manually acquired source table following RADAR license acceptance | `assets prepare-hivoto` |
| `hf_distilbert`, `hf_genderize` | Complete local model directories for `padmajabfrl/Gender-Classification` and `imranali291/genderize` | Separate acquisition, then `assets prepare-hf-model` |
| `local_llm` | Separately operated OpenAI-compatible endpoint and model | Explicit method configuration and the LLM worker profile |
| `hivoto_xgboost` | Model/vectorizer bundle plus an already registered HIVOTO lookup | `assets prepare-hivoto-xgboost`; experimental |

The commands and source requirements are described in [README.md](README.md#method-data) and
[the method reference](docs/20-method-adapters-reference.md). The experimental XGBoost JSON bundle
exists in the repository, but still needs registration; its distribution decision remains RG-05.

**Optional depends on the intended workflow.** The instance can start and perform basic classification
without separately registered assets. The published `reference_v1` aggregation requires all nine
reference methods; only HIVOTO-XGBoost is excluded. A smaller method selection does not make the
complete reference workflow ready. This is enforced in
[reference aggregation](backend/src/gendertagger/domain/aggregation.py) and specified in
[the scientific pipeline](docs/07-methods-and-aggregation.md#included-methods).

### Existing foundations to preserve

- Original sources, compiled SQLite lookups, and model files use immutable, content-addressed storage.
- Lookup metadata links source checksums, compiler/schema versions, SQLite versions, and record counts.
- Executions reference the exact selected artifact; scientific configuration uses digests rather than
  host filesystem paths.
- Fetch commands require expected checksums and enforce byte limits. Storage publishes atomically and
  verifies materialized bytes.
- API and workers share persistent artifact storage; the documented provisioning container uses the
  same database and artifact namespace.
- Local file import and offline inference are supported. Hugging Face loading explicitly uses local
  files; local LLM operation depends on the separately hosted endpoint.
- HIVOTO acquisition deliberately retains the interactive license-acceptance step.

These foundations are specified in
[ADR-0023](docs/decisions/ADR-0023-content-addressed-sqlite-method-lookups.md) and
[ADR-0024](docs/decisions/ADR-0024-hf-transformer-model-manifest-adapters.md), and implemented by
[artifact storage](backend/src/gendertagger/storage/local.py),
[lookup registration/resolution](backend/src/gendertagger/services/lookup_assets.py), and
[model materialization](backend/src/gendertagger/services/model_assets.py).

### Current gaps

1. **Readiness does not establish that the chosen workflow will work.**
   [`/ready`](backend/src/gendertagger/api/main.py) checks artifact-root path existence and PostgreSQL
   `SELECT 1`. It does not establish migration currency, storage writability/free space, asset
   availability, model loadability, queue consumers, coordinator operation, or LLM availability. The
   API container healthcheck uses the narrower `/health`. Operators assemble the remaining picture
   from [Compose](compose.yaml) and logs.

2. **Method discovery reports registration rather than operational availability.**
   [`GET /api/v1/methods`](backend/src/gendertagger/api/routes/methods.py) lists all ten adapters even
   when assets or LLM configuration are absent. The
   [descriptor contract](backend/src/gendertagger/models/method.py) contains scientific identifiers,
   versions, and confidence ranges, but no requirements, readiness states, remediation, or
   configuration schema. Consequently,
   [the run form](frontend/src/features/runs/NewRunForm.vue) uses raw JSON fields and cannot guide
   asset selection. Existing administrator settings cover branding, not provisioning.

3. **Acquisition, registration, and selection remain separate manual steps.**
   Operators must preserve the Compose mode/project name, mount private source directories, select
   upstream releases/revisions/checksums, run preparation commands, and copy `lookup_sha256` into
   project-run configuration. The [CLI](backend/src/gendertagger/cli/main.py) exposes `assets`,
   `users`, `projects`, and `teams`, but no setup, inventory, status, or verification command. There
   is no browser provisioning workflow.

4. **Validation happens at different depths and sometimes too late.**
   Lookup compilers perform structural checks, including requiring person and corporate-body records
   in a GND snapshot. However,
   [Hugging Face preparation](backend/src/gendertagger/cli/assets.py) registers every file in any
   nonempty directory without checking required tokenizer/configuration/weight files or attempting
   a model load. Private run creation validates configuration, and
   [scheduling](backend/src/gendertagger/services/execution.py) checks artifact registration;
   unavailable bytes or unloadable models can surface during execution.
   [Public classification](backend/src/gendertagger/services/public_classification.py) performs
   stronger byte/member checks before accepting work, but still does not establish model loadability.
   Its generic public failure response does not provide operator remediation.

5. **Storage supports repeated operations, but provisioning has no recovery workflow.**
   Re-registering identical bytes deduplicates safely. Downloads have no resume, backoff, or progress
   reporting, and preparations have no persisted status/checkpoints. A later GND download failure
   discards earlier temporary downloads. Model
   [cache materialization](backend/src/gendertagger/services/model_assets.py) accepts existing
   destinations without rechecking their bytes; its copy fallback is not published atomically, so
   an interrupted copy can be accepted on retry. Separately,
   [registration](backend/src/gendertagger/services/lookup_assets.py) returns existing metadata when
   identical bytes are supplied with amended provenance. Safe retries therefore need more than
   command reruns.

6. **Resource guidance and provenance validation are incomplete.**
   There is no consolidated matrix of acquisition sizes, retained disk space, temporary compilation
   space, RAM/VRAM, model compatibility, or throughput. Compose resource limits are not measured
   hardware recommendations. Sources and derivatives are retained, temporary copies coexist during
   preparation, and model materialization can create additional copies outside the mounted artifact
   volume. Models are cached per worker process without eviction, so concurrency affects memory.
   Current transformer adapters load on CPU, and the
   [registry](backend/src/gendertagger/services/method_registry.py) routes them to CPU despite the
   available GPU worker profile. Every backend installation includes the full ML dependency stack,
   intentionally under
   [ADR-0029](docs/decisions/ADR-0029-unconditional-method-dependencies.md). Selecting lightweight
   methods does not produce a lightweight installation.

   Source version and license metadata remain partly optional and operator-supplied. Model revision
   fields accept nonblank text rather than enforcing immutable upstream revisions. Checksums pin
   exact bytes, but do not validate the declared provenance or establish redistribution permission.
   There is no central license/access matrix or persisted license-acceptance record. Publication
   rights findings remain separate under RG-03 through RG-05.

7. **Offline operation is more complete than offline installation.**
   Locally supplied assets and inference avoid upstream downloads. The fresh-install guide still
   assumes network access for dependency/image acquisition. There is no documented end-to-end
   air-gapped installation or portable asset bundle carrying sources, derivatives, metadata, and
   selected configuration. Similarly, [`.env.example`](.env.example) describes `LLM_BASE_URL` only
   as an operator reference to copy into method configuration; it does not provision the model or
   automatically resolve the endpoint into `LocalLlmConfig`.

### Related operational limitations

[Backup](deploy/scripts/backup.sh) and [restore](deploy/scripts/restore.sh) scripts assume a particular
Compose container naming and named-volume layout; bind-mount installations require a corresponding
verified procedure. The original 2026-10-03 review found that the migration helper did not establish a
previous schema or expose readiness, despite completed-rehearsal claims in the implementation plan.
The [RG-13 correction](#rg-13-align-delivery-claims-with-implemented-and-verified-operations) retired that
helper and corrected the claims; local fresh-install/restore evidence does not remove the need for an
installation-specific upgrade/rollback rehearsal.

### Inputs to a future design

The strongest starting points are defining readiness for the chosen workflow, providing an authoritative
requirements/asset inventory, and connecting existing commands into one coherent lifecycle. Early model
validation, recoverable provisioning, measured resource guidance, and a documented offline installation
path address the main practical failure points. This analysis does not choose a CLI, browser interface,
or other guided entry point, and does not approve automatic download, model hosting, or deployment
automation.

Any design must preserve immutable artifact selection and provenance, manual acquisition where licensing
requires it, and durable API acceptance during broker outages. Infrastructure status and workflow
readiness need distinct meanings; optional broker/worker problems must not silently redefine the
scientific ensemble or erase accepted work. Operator diagnostics should be authorized and actionable,
while public responses retain their existing privacy boundaries. Pydantic contracts, application
services, FastAPI, generated frontend transport types, and identifier-only task envelopes remain the
architecture boundaries. Scientific changes require the governing design update and ADR before
implementation.

## Separate code-quality and consolidation review — 2026-10-03

The original review examined backend/frontend maintainability and repository/documentation quality
at HEAD `c9e3953ca97b8208de386ea3f7ac1042cb3779c1` plus the then-existing local changes. It changed only
this report. Evidence and line numbers below describe that historical tree; current defining-module
links and dated remediation/status entries identify the subsequent implementation.

**Scope assumption.** There are no production deployments and runtime backwards compatibility is not a
requirement for this cleanup. Prefer one supported current implementation over obsolete branches or
compatibility shims. Development data can be explicitly reset or reimported when an approved change needs
it. Scientific reference behavior, characterization evidence, accepted ADR history, immutable snapshots
and predictions, and append-only annotations remain governed by the architecture rules. Removing runtime
compatibility does not authorize rewriting scientific history. Revisit compatibility requirements in the
earlier RG plans when implementing them rather than carrying forward unnecessary pre-production readers.

Existing CI and local verification already distinguish the two applications. Passing lint/type checks
does not establish whole-program reachability or the absence of repetition. The new identifiers keep
these quality workstreams distinct from the functional and publication gaps above. P2 denotes substantial
shared-policy, boundary, or documentation work; P3 denotes smaller cleanup or discretionary extraction.
Current remediation status is recorded below; the original review evidence remains historical.

### Quality findings register

| ID | Priority | Area | Finding | Status |
|---|---|---|---|---|
| BQ-01 | P2 | Backend | Copied diagnostic formatters have inconsistent credential redaction | Fixed; shared formatter and persisted/API smoke verified |
| BQ-02 | P3 | Backend | Redundant helpers and dormant recovery/authentication surfaces remain | Helpers fixed; authentication extension decision deferred |
| BQ-03 | P2 | Backend | Worker retry policy and infrastructure construction are copied | Fixed; shared process owner, retry windows, real-worker and fork/reset checks passed |
| BQ-04 | P3 | Backend | Three executors repeat transaction, retry, and terminal-failure policy | Fixed; shared attempt policy with explicit resource transactions and passing lifecycle checks |
| BQ-05 | P2 | Backend | Dispatch persistence repeats common intent handling and field projection | Fixed; six-target PostgreSQL insertion, replay, race, lease, and recovery checks passed |
| BQ-06 | P3 | Backend | Historical runtime snapshot/configuration compatibility can be retired | Deferred; fingerprint representation and development-data reset need approval |
| BQ-07 | P2 | Backend | The dead-code gate counts words rather than application reachability | Deferred; framework/protocol roots and exemption scope need a design decision |
| FQ-01 | P2 | Frontend | Query keys, cursors, polling, and invalidation need shared ownership | Fixed; shared keys/cursor/polling and retained-context regressions passed |
| FQ-02 | P2 | Frontend | Shared domain UI and helpers remain coupled to feature folders | Fixed; defining shared modules and migrated consumers, without compatibility re-exports |
| FQ-03 | P2 | Frontend | Artifact interfaces duplicate canonical Pydantic contracts | Fixed; generated schemas, parser boundaries, and stored-byte HTTP identity exercised |
| FQ-04 | P2 | Frontend | Dialog structure and overlay styling are implemented repeatedly | Fixed; shared HeadlessUI shell, caller-owned safeguards, and native Escape/focus proof |
| FQ-05 | P2 | Frontend | Creation disclosure and cursor-list feedback are copied between views | Fixed; shared disclosure/list feedback, retained-draft and distinct failure recovery checks passed |
| FQ-06 | P2 | Frontend | Lifecycle, provenance, prediction, and annotation-history presentation repeat | Fixed; data-only presenters preserve uncertainty, confidence, and history semantics |
| FQ-07 | P2 | Frontend | Repeated native fields bypass incomplete shared field primitives | Fixed; shared native field composition and typed/null/boolean/accessibility checks passed |
| FQ-08 | P3 | Frontend | An orphan component, unused exported types, and dead CSS survive checks | Fixed; obsolete code removed and a bounded production-root graph gate covers files/exports/types/imports |
| DQ-01 | P2 | Documentation | Overlapping guidance and undated reports now disagree | Fixed; current owners/routes reconcile and historical records identify their evidence limits |
| DQ-02 | P2 | Documentation | The documentation gate omits maintained files and section targets | Fixed; explicit maintained/archive scope, aligned hooks, and offline heading-fragment checks passed |
| DQ-03 | P3 | Repository | Generated paper output and disposable development metadata are tracked | Deferred; manuscript build ownership and paper/tool-capture retention need approval |
| DQ-04 | P3 | Repository | Exact research/manuscript copies lack a deliberate archival policy | Deferred; archival retention and clearance need approval |

### Backend findings

#### BQ-01: Centralize persisted diagnostic formatting

**Evidence.** URL-credential redaction and 500-character truncation are repeated in
[aggregation execution](backend/src/gendertagger/services/aggregation_execution.py), line 50;
[evaluation execution](backend/src/gendertagger/services/evaluation_execution.py), line 42;
[export execution](backend/src/gendertagger/services/export_execution.py), line 55; and
[dispatch](backend/src/gendertagger/services/dispatch.py), line 96.
The same-named helper in [batch execution](backend/src/gendertagger/services/execution.py), line 52,
only truncates. A synthetic exception containing URL credentials was redacted by the other four helpers
but retained by the batch helper. Batch failure persists that text at line 330; the
[run repository](backend/src/gendertagger/db/repositories/run_repository.py), line 599, can copy it to
the method diagnostic exposed by `MethodExecutionSummary`. This confirms implementation drift and an
exposure path, not a deployed credential incident.

**Plan.** Use one application-layer formatter for detailed persisted diagnostics, with explicit disclosure
policies at boundaries. Preserve snapshot import's fixed safe messages and public classification's
limited failure codes rather than replacing them with detailed exceptions.

**Closure.** Duplicate formatters are removed; synthetic credential markers do not reach persisted/API
diagnostics; retry, truncation, and terminal-failure behavior remain covered by relevant regressions.

**Remediation (2026-10-04).** All five operational paths now use
[one application formatter](backend/src/gendertagger/services/diagnostics.py). URL user information is
redacted before the existing 500-character truncation, while retry and terminal-failure policy remains
resource-specific. Public snapshot-import messages and anonymous-classification failure codes are
intentionally unchanged.

Focused verification passed 35 unit/service cases and the PostgreSQL batch-to-execution regression.
An owned PostgreSQL smoke executed a failing batch, authenticated through the production Argon2/session
path, and read `/api/v1/runs/{id}/executions`: both persisted and HTTP diagnostics contained the redacted
URL and no synthetic credential marker. This does not claim general exception-text sanitization or
publication-commit verification.

#### BQ-02: Retire redundant helpers and decide the scope of dormant surfaces

**Evidence.** [Tabular ingestion](backend/src/gendertagger/ingestion/tabular.py), line 144, defines
`version_for_profile` with consumers only in two test modules. Production uses
[the import registry](backend/src/gendertagger/ingestion/registry.py), lines 21–28, which already returns
the canonical tabular parser version. `list_recoverable_jobs` in the
[public-classification port](backend/src/gendertagger/services/ports/public_classification_repository.py),
line 66, and [repository](backend/src/gendertagger/db/repositories/public_classification_repository.py),
line 155, is called only by repository tests; actual recovery is implemented in the
[dispatch repository](backend/src/gendertagger/db/repositories/dispatch_repository.py), lines 723 and 948.

`RejectAllAuthenticationBackend` in
[request authentication](backend/src/gendertagger/api/authentication.py), line 41, has no source or test
instantiation, while [application composition](backend/src/gendertagger/api/app.py), line 99, defaults
to the database provider. The security specification still explicitly offers the reject-all provider, so
this is a dormant supported-extension decision, not an unqualified dead-path defect.

**Plan.** Use the import registry in tests and remove its redundant mapper. Remove the unused recovery
surface unless a concrete workflow needs it. Decide whether the reject-all implementation still earns
a documented, tested extension contract; if retiring it, update current guidance while retaining ADR
history and the provider-neutral boundary.

**Closure.** Every retained surface has an application consumer or an explicit tested extension purpose.
Do not remove persistence assertion seams such as `get_dispatch` or `get_prediction`, framework
callbacks, or development seeding operations solely because they lack ordinary application callers.

**Remediation (2026-10-04).** The redundant tabular import-version mapper and repository/port recovery
enumerator are removed. Tests use the canonical import registry and actual dispatch recovery/lease
transitions. Real JSON, CSV, and XLSX imports completed through Celery with the canonical parser version;
public-job missing-intent and expired-lease recovery completed without reopening immutable results.
`RejectAllAuthenticationBackend` remains unchanged pending a supported-extension decision.

#### BQ-03: Reuse worker retry policy and infrastructure ownership

**Evidence.** The same two-second base, sixty-second cap, and jitter calculation occurs in
[batch tasks](backend/src/gendertagger/tasks/execution.py), line 38;
[aggregation tasks](backend/src/gendertagger/tasks/aggregation.py), line 33;
[evaluation tasks](backend/src/gendertagger/tasks/evaluation.py), line 35;
[export tasks](backend/src/gendertagger/tasks/export.py), line 35;
[import tasks](backend/src/gendertagger/tasks/snapshot_import.py), line 31; and inline in
[public classification](backend/src/gendertagger/tasks/public_classification.py), line 103.
A configurable bounded implementation already exists in
[dispatch services](backend/src/gendertagger/services/dispatch.py), lines 55 and 81.
These workers also independently construct settings, engines, session/UoW factories, and disposal
registration; classification adds repeated lookup/model-resolver assembly. A process serving several
task families can consequently own several pools.

**Plan.** Reuse one retry primitive with explicit existing defaults and attempt numbering. Extract a
process-owned worker infrastructure context for database, storage, resolvers, and resource disposal.
Keep task names, Pydantic envelopes, executor selection, and resource-specific retry limits/exceptions
explicit. Worker composition belongs outside FastAPI and still calls application services directly.

**Closure.** One retry algorithm and one resource-ownership path serve the workers. Existing envelope,
routing, retry, and concurrency checks pass; imports remain lazy; shutdown and process reinitialization
dispose or recreate owned resources correctly.

**Remediation (2026-10-04).** All six task families use the existing bounded jitter primitive with
their unchanged attempt numbering and limits. One lazy process owner supplies the pool, fresh UoW/session
scopes, storage, and classification-only resources. Shutdown/reset and fork hooks close owned idle
pools or detach inherited pools without closing parent connections. All six real Redis worker paths
passed; concurrent PostgreSQL scopes used distinct sessions/backends, and actual child reset/reinitialization
preserved the live parent connection. Ordinary aggregation/evaluation/export composition required no
classification build identity.

#### BQ-04: Extract repeated executor policy without a universal pipeline

**Evidence.** [Aggregation](backend/src/gendertagger/services/aggregation_execution.py),
[evaluation](backend/src/gendertagger/services/evaluation_execution.py), and
[export](backend/src/gendertagger/services/export_execution.py) executors repeat attempt validation,
claim/duplicate-delivery handling, transactional completion, rollback before retry, and a fresh claim
before persisting final failure. Their calculations and artifacts differ, but much of the surrounding
failure policy is the same.

**Plan.** Consider small typed helpers for attempt validation, retry decisions, and terminal-failure
handling after rollback, plus common lifecycle test cases. Preserve explicit transaction ownership,
permanent exception lists, typed results, and each resource's scientific/artifact work. A universal
executor base class is not required; retain duplication where extraction would obscure those contracts.

**Closure.** Shared lifecycle policy has one maintained implementation where useful, and duplicate
delivery, transient rollback, final failure, and atomic completion still pass for all three resources.

**Remediation (2026-10-04).** One small typed helper validates positive attempt bounds and decides
the remaining unclassified-error retry budget for aggregation, evaluation, and export. Claims,
permanent exception lists, rollback, fresh terminal claims, and atomic scientific/artifact completion
stay explicit in each executor. Existing Core/PostgreSQL lifecycle regressions passed; actual completed
resource replays remained immutable. The complementary smoke did not repeat fresh computation or
fault-injected rollback; those branches remain covered by the existing lifecycle suites.

#### BQ-05: Consolidate common dispatch persistence mechanics

**Evidence.** The [dispatch repository](backend/src/gendertagger/db/repositories/dispatch_repository.py)
contains six `_ensure_*_dispatch` branches starting at lines 126, 171, 223, 286, 343, and 400. Each repeats
insert defaults, conflict-ignore, flush, retrieval, matching-intent validation, and typed return.
`_dispatch_from_row`, lines 1171–1309, repeats operational fields in six constructors; recovery repeats
target candidate construction as well.

**Plan.** Extract narrowly scoped persistence helpers for common insert/intent retrieval and dispatch
field projection. Preserve explicit Pydantic variants and target-specific existence, lifecycle, queue,
ownership, and exactly-one-target checks. Keep ORM rows inside persistence; avoid an untyped generic
repository. Coordinate public-job recovery with BQ-02.

**Closure.** Common operational fields and intent behavior have one maintained path. PostgreSQL checks
still cover every target, concurrent idempotent creation, mismatched intent, leases, missing/stale
recovery, and target-specific invariants.

**Remediation (2026-10-04).** Typed same-file helpers share conflict-ignore insertion, flush/retrieval,
intent matching, and the operational-field projection across all six target variants. Target validation,
envelopes, recovery candidates, queue selection, and lock/lease policy remain explicit. Six-kind
PostgreSQL race/replay checks preserve immutable intent and operational timestamps/leases; the complete
PostgreSQL and real Redis suites passed. Actual broker unavailability returned the claimed intent to
pending with its lease cleared and next retry persisted.

#### BQ-06: Remove runtime compatibility maintained only for old development state

**Evidence.** [Person fingerprinting](backend/src/gendertagger/services/execution.py), lines 75–87,
removes absent `name_forms` and empty `events` specifically to preserve historical hashes;
[its regression](backend/tests/services/test_person_fingerprints.py), line 44, fixes that old
representation. [Snapshot persistence](backend/src/gendertagger/db/repositories/project_repository.py)
derives missing statistics for legacy ready snapshots at lines 259–286, although current import persists
statistics and completion requires them. `_source_packaging`, line 803, defaults absent persisted
packaging to `single` despite the canonical import-configuration validation path.

**Plan.** Specify one current snapshot/configuration/fingerprint representation, reset or reimport old
development data explicitly, and retire obsolete reconstruction/defaulting paths. Update the governing
design and add an ADR before changing fingerprints/provenance. Preserve published scientific semantics
and historical characterization fixtures; do not mutate successfully imported snapshots or predictions.

**Closure.** Current imports always persist complete provenance/statistics; malformed current persistence
fails explicitly; fingerprints use the approved representation; relevant migration, provenance, and
scientific checks pass without runtime support for obsolete development state.

**Disposition (2026-10-04).** Deferred under the requested open-question boundary. No fingerprint,
legacy snapshot reconstruction, packaging default, or development-data reset changed. Closure requires
an approved current fingerprint/provenance representation and an explicitly authorized reset/reimport,
with the governing design/ADR recorded before cutover.

#### BQ-07: Make dead-code checks distinguish references from reachability

**Evidence.** [The current checker](backend/scripts/check_dead_code.py), lines 119–131 and 188–205,
counts identifier words throughout Python source, tests, comments, and strings. It does not resolve
imports or distinguish identically named methods. Lines 17–39 and 114–116 exempt broad decorator names,
including every static/class method. In-memory probes produced zero diagnostics for an orphan function
mentioned only in a comment, a self-recursive orphan, and an unused static method. The checker passes on
the current tree; that pass does not demonstrate that production code is reachable.

**Plan.** Add or evolve analysis of import/call references rooted in actual API/CLI/Celery entry points.
Separate production reachability from test references, with narrow explicit framework/protocol and
supported-extension exemptions. Exclude comments/strings from ordinary reference counts and handle
recursive orphan groups. Keep Ruff and Import Linter for their complementary purposes.

**Closure.** Regression cases detect comment-only references, isolated recursion, and orphan decorated
helpers, while real FastAPI dependencies, Pydantic validators, Celery registrations, and protocols pass.
Unused-code evidence identifies the owning symbol rather than relying on global name occurrences.

**Disposition (2026-10-04).** Production reachability changes remain deferred until the Python graph's
FastAPI/CLI/Celery roots and narrow framework, protocol, and supported-extension exemptions are agreed.
The existing heuristic is retained and documented as such; its passing result is not production
reachability evidence. The frontend uses a separate bounded production-root graph (FQ-08).

### Frontend findings

#### FQ-01: Share query ownership, cursor mechanics, and list polling

**Evidence.** [Aggregation queries](frontend/src/composables/useAggregations.ts), line 36;
[evaluation queries](frontend/src/features/evaluation/useEvaluations.ts), line 31; and
[export queries](frontend/src/features/export/useExports.ts), line 25, repeat infinite-query setup,
cursor continuation, two-second live-item polling, and creation invalidation. Source contains 21
`initialPageParam` setup sites. Detail polling already has
[a shared composable](frontend/src/composables/usePolledQuery.ts).
Snapshot reads in `useSnapshotImport`/`useSnapshotData` and run reads in `useRunDetail`/`useTaskData`
also use different keys for equivalent resources. Principal/request ownership differs between older
run/artifact queries and newer snapshot/task/admin queries; annotation invalidation independently knows
literal cache layouts in [useAnnotate](frontend/src/composables/useAnnotate.ts), lines 54 and 78.

**Plan.** Establish shared typed resource key/options builders, cursor helpers, and list polling.
Keep endpoint request functions, filters, and lifecycle predicates explicit. Move `currentData` out of
the project feature into shared query support. Apply one principal/cancellation convention to reads,
writes, and invalidation, using the same key definitions everywhere. This is the consolidation path
for RG-02 and supports RG-12; it does not replace those correctness fixes.

**Closure.** Cursors remain tied to their exact principal/resource/filter/sort context; late requests
cannot update a replacement account; polling and cancellation retain correct lifecycle behavior; shared
invalidation refreshes all affected projections. Preserve the account/route regression coverage.

**Remediation (2026-10-04).** Shared typed resource/principal keys, current-data guards, opaque cursor
options, and canonical-page live-list polling replace the duplicated ownership mechanics. All 21
original continuation sites use the shared options; snapshot/artifact intervals and error policies,
inspection/import-status differences, SSE, and annotation invalidation remain explicit. The covered
frontend suite and account/route/cursor regressions passed; the actual browser switched review queues
and received the exact seven-record server page under the replacement filter tuple.

#### FQ-02: Move already-reused domain presentation into shared modules

**Evidence.** [The coding guidelines](docs/26-frontend-coding-guidelines.md) forbid cross-feature
imports, but [VocabBadge](frontend/src/components/domain/VocabBadge.vue) serves review, game, method
results, and project statistics from the review feature. [GameModeView](frontend/src/features/game/GameModeView.vue),
lines 14–31, imports person presentation, badges, names, retention logic, annotations, reads, filters,
and vocabulary from other features. Project snapshot panels import review person details; evaluation
imports review vocabulary. Shared lifecycle translation remains owned by
[runs](frontend/src/composables/useStatusLabel.ts).

**Plan.** Promote vocabulary badges, person details, and lifecycle presentation into the documented
`components/domain/` location. Move common token/gloss/name helpers into shared domain modules and
stateful resource reads into shared composables/query support. Keep screen orchestration in features
and make dependency direction explicit; a new barrel that preserves feature coupling is insufficient.

**Closure.** Shared presentation has no feature dependency; consumers import defining shared modules;
canonical tokens, uncertainty distinctions, translation, colors, and original source text remain intact.
Enforce the boundary or document narrow justified exceptions.

**Remediation (2026-10-04).** Nineteen already-shared modules moved to their defining `components/domain/`
or `composables/` owners, with semantic references and Vue module/template edges mapped before cutover.
Common queue descriptors and the native review-items query are shared; review filters/routes stay local,
and game mode owns its open/full tuple. All consumers migrated directly, without old-path barrels,
aliases, or compatibility re-exports. Shared source/person/vocabulary presentation rendered through the
actual private API in review, method results, and the synthetic game fixture.

#### FQ-03: Generate artifact types from their canonical contracts

**Evidence.** [exportDownload](frontend/src/features/export/exportDownload.ts), lines 10–29,
handwrites `ExportManifestOutput` and `ExportManifest`, despite generated versions in
[the transport schema](frontend/src/api/schema.d.ts). The mirror widens format/policy/profile values
and differs in optionality. [useExports](frontend/src/features/export/useExports.ts), line 12,
declares an unused generated manifest alias. [reportSchema](frontend/src/features/evaluation/reportSchema.ts),
lines 3–69, mirrors backend evaluation models because the report-download endpoint is untyped in OpenAPI.
Both artifact parsers are live and serve a necessary runtime validation role.

**Plan.** Use generated export-manifest types and delete handwritten mirrors and the dead alias. Expose
the canonical evaluation report schema accurately through the API contract and regenerate transport
types while preserving checksummed stored-byte delivery. Retain runtime artifact discrimination and
shape checks; generated TypeScript alone does not validate downloaded JSON.

**Closure.** Artifact shapes have one Pydantic authority reflected in generated TypeScript; malformed
artifacts still fail safely; exact artifact bytes/checksums and scientific definitions remain unchanged.
Coordinate future manifest work with RG-15 without adding obsolete readers merely for development data.

**Remediation (2026-10-04).** Report and manifest mirrors and the unused manifest alias are removed.
The report endpoint advertises `EvaluationReport` while retaining raw stored-byte delivery; the OpenAPI
snapshot and frontend transport were regenerated through the existing generators. Parsers retain
structural discrimination, canonical vocabulary checks, nullable/omitted optional fields, finite values,
and zero-valued evidence.

Focused parser/download verification passed 38 cases, and the complete PostgreSQL profile passed the
report byte/hash regression. A real authenticated API smoke compared its 7,777-byte report with the
persisted artifact and SHA-256 `fa1705020f39e343d48c38922a7ecdaad8d3049779589ab1e7fbb29d37e80611`.
Chromium fetched and parsed the same bytes through the production frontend parser and displayed the
evaluation sections. This is byte/contract verification, not full UI accessibility conformance.

#### FQ-04: Reuse a presentational dialog shell

**Evidence.** Separate HeadlessUI dialog/backdrop/panel/title/action compositions occur in
[DraftLeaveDialog](frontend/src/app/DraftLeaveDialog.vue), line 13;
[SessionRecoveryDialog](frontend/src/features/auth/SessionRecoveryDialog.vue), line 37;
[AdminUserEditForm](frontend/src/features/admin/AdminUserEditForm.vue), line 200;
[AdminUserSecurityActions](frontend/src/features/admin/AdminUserSecurityActions.vue), line 140;
[AdminSettingsEditor](frontend/src/features/admin/AdminSettingsEditor.vue), line 542;
[AdminTeamsView](frontend/src/features/admin/AdminTeamsView.vue), lines 802 and 835; and
[ProjectMembershipView](frontend/src/features/projects/ProjectMembershipView.vue), line 272.
They copy overlay positioning, panel surface, radius, and shadow CSS.

**Plan.** Extract an `AppDialog` shell around existing HeadlessUI behavior with named body/title/action
slots and bounded size options. Keep confirmation state, pending-write dismissal, credential display,
recovery, and draft ownership at the feature call site. Keep the mobile drawer's distinct behavior.

**Closure.** Shared overlay geometry and semantics replace copied markup/CSS while retaining focus
trapping/restoration, accessible naming, Escape/backdrop policy, and pending-operation safeguards.

**Remediation (2026-10-04).** Existing confirmations, recovery, project switching, and administration
dialogs adopt the shared HeadlessUI `AppDialog` shell and delete copied overlay geometry. Callers retain
pending-write dismissal, credentials, draft/recovery state, and other feature policy. The dialog suites
passed; native Chromium Escape cancelled a dirty-draft leave dialog and returned focus to the initiating
Projects link. Obsolete source-markup/CSS recipe assertions were retired rather than re-pinned;
behavioral dialog/field suites and actual desktop/mobile surfaces remain the verification boundary.

#### FQ-05: Share creation disclosure and cursor-list feedback

**Evidence.** [RunListView](frontend/src/features/runs/RunListView.vue), lines 40–59;
[EvaluationListView](frontend/src/features/evaluation/EvaluationListView.vue), lines 30–49; and
[ExportListView](frontend/src/features/export/ExportListView.vue), lines 35–55, repeat form disclosure,
deferred mounting, heading focus, and account/route resets. Their loading, first-load error, retained-row
refetch error, next-page feedback, retry, and load-more compositions also repeat. `AppFeedback` and
`AppButton` already cover primitives, but not this repeated composition.

**Plan.** Extract a small creation-disclosure composable/component and cursor-list feedback/footer
with explicit states, labels, events, and slots for domain content. Keep permissions, resource context,
forms, and business rules explicit rather than creating a configuration-driven universal workflow page.

**Closure.** These workflows share disclosure and pagination presentation; ordinary hide/show preserves
drafts; account/resource/access changes reset correctly; deliberate opening moves focus; initial,
refetch, and next-page failures retain distinct recovery behavior.

**Remediation — 2026-10-04.** Run, evaluation, and export lists use `useDisclosure` and `AppCursorList`.
Ordinary collapse retains the mounted draft and navigation guard; principal, password, resource, and
access changes reset ownership. Deliberate opening focuses the form heading. Cursor recovery retains
loaded rows and distinguishes initial, refetch, and continuation failures; busy actions cannot submit
duplicate requests. Native browser hide/show retained a configured run draft, and Escape from its
leave confirmation returned focus to the invoking link.

#### FQ-06: Reuse lifecycle, provenance, prediction, and history presenters

**Evidence.** Lifecycle text/color repeats in
[RunItem](frontend/src/features/runs/RunItem.vue), line 120;
[EvaluationItem](frontend/src/features/evaluation/EvaluationItem.vue), line 73;
[ExportItem](frontend/src/features/export/ExportItem.vue), line 59, and their detail views.
[RunProvenance](frontend/src/features/runs/RunProvenance.vue),
[AggregationDetailView](frontend/src/features/runs/AggregationDetailView.vue), and
[EvaluationDetailView](frontend/src/features/evaluation/EvaluationDetailView.vue) independently render
resolved JSON and selected execution names/versions. Prediction badge/status/confidence/missing-output
cells repeat in [ReviewDetail](frontend/src/features/review/ReviewDetail.vue), lines 315–355;
[GameModeView](frontend/src/features/game/GameModeView.vue), lines 1037–1077; and
[MethodExecutionResultsView](frontend/src/features/runs/MethodExecutionResultsView.vue), lines 298–328.
Annotation history repeats in ReviewDetail and
[SnapshotAnnotationDetail](frontend/src/features/review/SnapshotAnnotationDetail.vue), lines 104–172.

**Plan.** Extract small domain presenters for status, JSON disclosure, selected executions, and prediction
cells/evidence; share annotation-history presentation within review. Extend existing vocabulary,
feedback, scroll-region, and provenance foundations. Use these responsibilities to split mixed screens
such as GameModeView; file length alone is not the reason. Presenters receive data and do not fetch it
or make scientific decisions.

**Closure.** Real consumers adopt the presenters and delete replaced rendering/CSS. Missing output,
`unknown`, `abstain`, `error`, and method-specific confidence stay distinct. Annotation ordering and
audit history remain server-authoritative.

**Remediation (2026-10-04).** Data-only lifecycle, JSON/provenance, selected-execution,
prediction/status/confidence/missing-output, and review-local annotation-history presenters replace
copied rendering/CSS in their real consumers. Boundary regressions preserve zero/null confidence,
missing versus abstain/error/unknown, original source text, and append-only ordering/attribution.
Actual Chromium surfaces displayed lifecycle/provenance/report metadata, method output, review queues,
and the synthetic game source record; scientific decisions remain server-owned.

#### FQ-07: Extend and adopt shared field composition

**Evidence.** [AppTextField](frontend/src/components/base/AppTextField.vue), lines 6–20, handles labels
and errors but lacks explicit help/description composition and targeting for several input attributes.
Project slug, export responsibility, branding inputs, and checksum verification therefore handwrite
field wiring in [ProjectCreationForm](frontend/src/features/projects/ProjectCreationForm.vue),
[NewExportForm](frontend/src/features/export/NewExportForm.vue),
[AdminSettingsEditor](frontend/src/features/admin/AdminSettingsEditor.vue), and
[ExportDetailView](frontend/src/features/export/ExportDetailView.vue).
Single-line styling repeats across the primitive, project form, and personal settings; native-select
label/control/description composition repeats across settings, membership, review, and artifact forms.

**Plan.** Extend the field primitive with explicit child-input attributes and label/help/error slots,
then adopt it for compatible text fields. Use a small native-select field or shared field wrapper for
the repeated composition. Keep ordinary selects native and field-specific validation in features.

**Closure.** Common fields share label/help/error relationships, disabled/invalid states, and sizing;
browser constraints, descriptions, focus, and feature-specific validation are preserved.

**Remediation (2026-10-04).** `AppField`, native `AppSelectField`, and extended `AppTextField` compose
label/help/error IDs and forward native attributes/listeners to their controls, not layout wrappers.
Compatible forms/settings/filters migrated; specialized textarea/file/radio/checkbox controls remain
native. Vue's normalized camel-case ARIA props now preserve external description IDs alongside local
help/error IDs. Native null/boolean choices survive failed save and explicit retry; the actual settings
surface had no missing description targets and persisted German/dark/expanded preferences through the
ordinary API. Validation and uncertainty semantics remain feature/server-owned.

#### FQ-08: Remove confirmed orphan frontend code and cover unused exports

**Evidence.** The former `frontend/src/components/base/AppListbox.vue` had no application import,
router registration, or dynamic/global reference; its only consumer is its component test.
[SidebarPreferences](frontend/src/app/SidebarPreferences.vue), lines 182–243, implements its own
HeadlessUI listboxes. The delivery plan still claims the live switchers use AppListbox. Six exported
type aliases have no callers in source/tests: `AppI18n` in `app/i18n.ts:63`, `ExportManifestRecord` in
`features/export/useExports.ts:12`, `TaskRun` in `features/tasks/useTaskData.ts:11`, `ProjectTeam` and
`ProjectManagerCandidate` in `features/projects/useProjectCreation.ts:8–9`, and `SnapshotStatistics` in
`features/projects/useSnapshotData.ts:9`. The `.admin-teams-list-items` selector in
[AdminTeamsView](frontend/src/features/admin/AdminTeamsView.vue), line 1009, is also unused.

**Plan.** Either adapt AppListbox to SidebarPreferences' actual slot, disabled, tooltip, and focus needs
and use it, or remove the orphan, its dedicated tests, and stale claims. Remove dead aliases/CSS and
make internally used exports private where appropriate. Add application-reachability/unused-export
analysis with explicit treatment of Vue templates, lazy routes, dynamic uses, tooling, tests, and
generated contracts. `noUnusedLocals` and `noUnusedParameters` do not detect these cases.

**Closure.** Production components have application consumers or an explicit catalog purpose; dead
aliases/selector and stale claims disappear; the new check catches equivalent orphans. No other orphan
Vue component or definitively unused runtime dependency was confirmed in this review.

**Remediation — 2026-10-04.** Removed the orphan AppListbox and its dedicated tests, unused aliases,
and dead admin-team CSS; internally used declarations are private and live consumers import defining
modules directly. Pinned development-only Knip 6.39.0 checks the browser graph rooted exclusively at
`src/main.ts`, including Vue templates and lazy imports. Tests/configuration cannot rescue dead
application code. Generated OpenAPI declarations exempt only unused export/type diagnostics, not
file reachability or unresolved imports. Behavioral analyzer fixtures exercise orphan, template,
lazy-route, test-only, generated-schema, and unresolved-import boundaries. Local checks, pre-commit,
and GitLab run the same gate; the final production graph passed.

### Repository and documentation findings

#### DQ-01: Give current guidance one owner and label historical records

**Evidence.** [The UI inventory](docs/23-wireframe-ui-inventory.md), lines 441 and 554, says personal
settings UI is deferred; [the delivery plan](docs/24-frontend-delivery-plan.md), line 327, and the router
show it delivered. [The integration contract](docs/17-frontend-integration.md), line 119, puts its link
in the sidebar footer, while the delivery plan and current shell place it in the account menu.
[The frontend README](frontend/README.md), line 180, describes independent branding fetches even though
the current implementation shares a query. [audit.md](audit.md) is undated and lists skip-link and
critical-text contrast work now present in code/tests. [IDEAS.md](IDEAS.md) duplicates publication,
verification, sample-data, and repository-polish tasks now maintained in this report.

**Plan.** Keep AGENTS/SPEC as concise entry points; docs/15 owns sequencing, docs/17/25/26 current
frontend contracts/design/code rules, docs/22 deferred capabilities, and RELEASE_GAPS actionable release
findings. Reduce overviews to operational instructions and source links. Reconcile current documents;
mark delivery/verification reports with dates, revisions, and resolved/superseded status. Preserve accepted
ADRs and deliberate historical records. Cross-reference RG-13 for existing inaccurate delivery claims.

**Closure.** Each concern has one maintained owner; current guidance agrees with routes/contracts;
historical reports cannot be mistaken for current requirements; duplicate open checklists link to the
authoritative register.

**Remediation — 2026-10-04.** Current guidance agrees on the delivered account-menu settings route,
shared branding query, and defining presentation modules. The UI inventory and delivery plan identify
their historical baseline and current-versus-proposed scope. The audit explicitly records that its
original date/revision were not captured; its superseded checklist points here. IDEAS links release
work to this register instead of maintaining a competing checklist. SPEC's quickstart target and the
historical changelog's missing-PLAN reference are corrected without rewriting accepted ADRs.

#### DQ-02: Align documentation discovery, hooks, and local-link validation

**Evidence.** [The documentation checker](backend/scripts/check_documentation.py), lines 13–22 and
133–151, scans selected root files, the frontend README, and Markdown under docs. It omits DESIGN,
PRODUCT, IDEAS, audit, CHANGELOG, RELEASE_GAPS, and backend/contracts READMEs, although hooks match
root Markdown and those READMEs. The ordinary checker passes; direct use of its existing file validator
finds `CHANGELOG.md:17` linking to missing `PLAN.md` and `audit.md` lacking an H1. It also ignores section
fragments: [SPEC.md](SPEC.md), line 4, links to `README.md#quickstart`, but that heading does not exist.

**Plan.** Explicitly distinguish maintained documents from archived evidence and use the same inventory
in policy, hooks, and CI. Include this report when retained. Validate supported heading fragments offline,
including repeated headings, front matter, fenced examples, and the chosen renderer's slug rules.

**Closure.** All intended maintained files enter the gate; missing files and section targets fail; valid
links pass; archival treatment is explicit. Do not hide the omissions by weakening Markdown rules.

**Remediation — 2026-10-04.** The checker requires the documented root/application README inventory
and maintained design/ADR tree. Paper/poster history is exempt from structural maintenance, but
inbound local links still validate its targets. Hooks cover that inventory and archival target
changes; CI/push checks run the policy. Offline fragment validation handles rendered inline text,
Unicode and strict percent-decoding, duplicate IDs, ATX/Setext headings, front matter, and fences.
Missing targets produce `DOC203`; path/encoding violations retain `DOC201`. The current repository
passed the real command, and deterministic policy regressions cover valid and invalid boundaries.

#### DQ-03: Stop tracking disposable build and tool metadata

**Evidence.** Git tracks paper intermediates `article.aux`, `.blg`, `.fdb_latexmk`, `.fls`, `.out`, and
`.synctex.gz`; the root ignore rules cover logs but not those intermediates. The `.fls`/`.fdb_latexmk`
files retain developer-specific paths. [.impeccable/live/app-root.json](.impeccable/live/app-root.json)
records an absolute workspace path, and [.impeccable/design.json](.impeccable/design.json) is a dated
generated snapshot with old `male-blue`/`female-coral` tokens that differ from DESIGN and current CSS.
[The paper README](docs/paper/README) still describes an empty upstream template and an absent
`preface.tex`; `instruct.tex` refers to missing `frontmatter`.

**Plan.** Untrack reproducible LaTeX intermediates and ignore them. Define one manuscript build path and
deliberately choose which PDFs or bibliography outputs are retained publication artifacts. Preserve
required class/style/logo resources; remove or archive unused template examples and manuscript scraps
after identifying their purpose. Ignore transient live-tool metadata. Regenerate optional design
snapshots reproducibly or identify them as historical evidence; retain review captures only with a
deliberate dated verification purpose. This cleanup is separate from RG-03–05 clearance decisions.

**Closure.** A clean manuscript build creates no unintended tracked changes; every retained paper/tool
file has a documented purpose; builds do not depend on developer paths; current design sources agree.

**Disposition — 2026-10-04: deferred.** No tracked manuscript output, template resource, tool capture,
or design snapshot was removed or newly ignored. Choosing the maintained manuscript build and retained
publication/review artifacts requires an explicit retention decision; reproducibility and purpose are
not established merely by a generated-looking filename. The documentation gate's archival structural
exemption is not deletion approval. Current frontend guidance is reconciled independently.

#### DQ-04: Consolidate verified duplicate artifacts with recorded provenance

**Evidence.** Byte and SHA-256 comparisons confirmed these identical pairs:

- `data/output_old/agreement_metrics_summary_20260226_012532.csv` and
  `data/output_old/agreement_metrics_summary_20260226_082608.csv`;
- `data/output_old/cohens_kappa_results_20260226_012532.csv` and
  `data/output_old/cohens_kappa_results_20260226_082608.csv`;
- `data/output_old/record_agreement_20260226_013002.csv` and
  `data/output_old/record_agreement_20260226_082639.csv`;
- `docs/paper/article.pdf` and
  `docs/paper/klappenbach,neuber,westphal_2026_gendertagger_revised.pdf`.

**Plan.** Retain one deliberate artifact per exact output and record historical aliases/run references
in an archival manifest where needed. Separate approved reproducibility evidence from transient output;
coordinate with RG-03/RG-16. Similar-looking `data/results` and `data/output/results` were not identical
and are not confirmed safe duplicates. Keep scientific characterization/reference fixtures intact.

**Closure.** Retained artifacts have purpose, origin, checksum, and appropriate clearance; necessary
historical aliases remain traceable; consolidation does not discard distinct study evidence.

**Disposition — 2026-10-04: deferred.** Exact byte identity establishes duplication, not permission to
discard a historical run or publication alias. Research CSVs, both manuscript PDFs, source references,
and scientific fixtures remain unchanged. Consolidation requires a chosen archival owner/location,
alias/provenance retention, and applicable publication/data clearance; no implicit reset or deletion
was performed.

### Suggested cleanup sequence

1. Establish maintained-document/artifact ownership and current-only runtime scope: DQ-01–04 and BQ-06.
   Preserve scientific decisions and evidence before selecting anything for removal.
2. Improve unused-code detection and remove confirmed orphans: BQ-02/BQ-07 and FQ-08. Use explicit
   extension decisions instead of keeping test-only production surfaces by default.
3. Consolidate shared correctness-sensitive policy: BQ-01/BQ-03 and FQ-01/FQ-03. Coordinate cache and
   contract changes with RG-02/RG-12/RG-15 and preserve their regression requirements.
4. Extract frontend domain UI, dialogs, fields, and repeated workflow presentation: FQ-02/FQ-04–07.
   Migrate real consumers and delete superseded markup/CSS in the same focused changes.
5. Simplify dispatch/executor internals where the shared policy is clear: BQ-04/BQ-05. Keep domain
   contracts and transaction ownership explicit. Run all applicable locked quality gates with each
   implementation change; RG-17 still requires one complete final release verification.

### Historical verification and limits of the original review — 2026-10-03

| Area | Check | Observed result |
|---|---|---|
| Backend | Existing dead-code, contract-naming, package-initializer policies | Passed |
| Backend | Ruff check and format check, without cache writes | Passed; 402 Python files already formatted |
| Backend | Source-reference/caller review and synthetic diagnostic comparison | Confirmed BQ-01/BQ-02 evidence; no database mutation |
| Backend tooling | In-memory orphan/comment/recursion/decorator probes | All three passed undetected, confirming BQ-07 limitations |
| Frontend | `npm --prefix frontend run lint` | Passed |
| Frontend | `npm --prefix frontend run typecheck` | Passed for source, tests, and Vite configuration; no emit |
| Frontend | `npm --prefix frontend run i18n:check` | Passed; two locales and 1,364 keys agree |
| Frontend | `npm --prefix frontend run api:check` | Passed; generated transport matches committed OpenAPI |
| Documentation | Existing documentation policy | Passed; its inventory/fragment limitations are DQ-02 |
| Documentation | Direct validation of excluded documents | Confirmed missing PLAN link and absent audit H1; report checked separately |
| Repository | Tracked-file inventory and artifact byte/hash comparison | Confirmed DQ-03/DQ-04; no removals |

The original report-only review used Python 3.11.15 and Ruff 0.16.2. Frontend checks used Node 26.10.0,
npm 12.2.0, ESLint 10.11.0, vue-tsc 3.3.11, and TypeScript 5.9.3. Existing dependencies were used without
installation or lockfile changes. No application test suites, service-backed checks, dependency audits,
package/production builds, manuscript builds, or browser visual assessment were rerun for this
report-only change. These static results supplement, and do not replace, the release verification record.

Useful foundations already exist: backend cursor/keyset helpers, explicit Pydantic ports, generated
frontend transport, shared detail polling, tokens/layout recipes, AppButton/AppFeedback/AppScrollRegion,
and reusable review decisions. Build on those rather than adding competing abstraction layers. Legacy
implementation material under ignored `__scrap/` and ordinary dependency/build caches are already excluded
from Git. Complementary mypy/Pyright checks and the separate backend/frontend dependency manifests have
documented purposes; this review found no basis to remove them as redundant.

### Implementation verification — 2026-10-04

Work ran in the isolated `/tmp/gendertagger-quality-20261004` worktree on
`quality/release-gap-consolidation`, based on `14420ce`; the concurrent original worktree was not
modified. Implementation and policy dispositions through `80e6da6` were committed in focused steps.
The quality register now contains 14 fixed findings, one partially fixed finding (BQ-02), and four
deferred findings (BQ-06/BQ-07/DQ-03/DQ-04). Authentication-extension, fingerprint/reset,
Python-root/exemption, and archival-retention choices remain explicit decisions, not hidden cleanup.

| Area | Exercised check | Observed result |
|---|---|---|
| Backend contracts/policy | Locked environment, naming, initializer, existing dead-code heuristic, Ruff format/lint | Passed; the heuristic still does not prove Python production reachability |
| Backend types/boundaries | mypy, Pyright, Import Linter | Passed; 400 mypy files, zero Pyright errors/warnings, six kept architecture contracts |
| Backend core | Locked core pytest profile | 1,822 passed |
| Backend PostgreSQL | Locked service-backed pytest profile | 347 passed, including dispatch replay/races/leases and immutable scientific/history boundaries |
| Backend Redis | Locked real-worker pytest profile | Seven passed; snapshot, batch, aggregation, evaluation, export, and public-classification task families exercised |
| Backend coverage | Combined three-profile evidence | 88.25%; normalization, aggregation, aggregation assessment, and TEI profile each 100% |
| Database/distribution | Alembic upgrade/check, locked wheel/sdist build and distribution policy | Passed; no new schema operations, both archives checked |
| Dependencies | Backend audit and frontend npm audit | No known vulnerabilities reported |
| Frontend source/contracts | Lint, Prettier, three TypeScript configurations, OpenAPI generation check, locale parity | Passed; two locales and 1,364 keys agree |
| Frontend behavior | Full coverage suite after source-markup/style tests were retired | 1,770 passed in 93 files; statements 91.15%, branches 85.50%, functions 87.92%, lines 92.60% |
| Frontend application graph | Pinned Knip production gate and behavioral graph fixtures | Passed; tests/tooling cannot rescue dead shipped code |
| Frontend distribution | Production Vite build | Passed; 2,073 modules transformed |
| Documentation | Real offline policy command and focused policy regressions | Passed; 44 regressions cover inventory, headings, links, and diagnostic boundaries |
| Browser | Owned authenticated synthetic project, desktop and 390-pixel mobile surfaces | Settings, evaluation, review, method results, game, source annotation history, run disclosure, and export validation observed |
| Visual detector | One Impeccable detection pass | One incumbent `AppSidebar.vue` width-transition finding remains; its style was not changed in this work |

Additional direct runtime proof used private fixtures, not production data:

- One process-owned pool supplied three fresh sessions/PostgreSQL backends. Ordinary artifact
  executors did not initialize classification metadata. A real fork rejected the inherited owner,
  reset/reinitialized child resources, and preserved the parent's live connection.
- Fresh JSON/CSV/XLSX imports completed with two canonical records each. A real `gender_guesser`
  batch and public CPU classification produced Anna/female and John/male while preserving raw output
  and normalization provenance. Missing/expired dispatch recovery completed; stale ownership was
  rejected and duplicate broker delivery did not change terminal evidence.
- A genuinely unavailable Redis endpoint left a claimed dispatch pending with its persisted retry
  deadline and cleared lease. Subsequent publication used the real Redis adapter.
- An authenticated evaluation-report download retained all 7,777 stored bytes and SHA-256
  `fa1705020f39e343d48c38922a7ecdaad8d3049779589ab1e7fbb29d37e80611`; OpenAPI advertised the canonical
  `EvaluationReport` without reserialization.
- Browser hide/show retained a configured run draft. Native Escape cancelled the leave dialog and
  returned focus to its invoking link. The contested/all review queues showed two/seven synthetic
  people; source history retained attribution, supersession, and revisions. A game decision used the
  real append-only annotation path.
- Native settings submitted JSON `locale: null` and `desktop_sidebar_collapsed: false`, not strings;
  the stored response retained those types. Invalid visible TEI responsibility input set
  `aria-invalid`, referenced existing hint/error elements, and disabled submission. Mobile width and
  scroll width were both 390 pixels. Final browser error/console-error collections were empty.

Limits: the standalone aggregation/evaluation/export pool smoke replayed completed resources; fresh
computations and failure branches were exercised by the service-backed suites. Local LLM acceptance
and queue routing were observed, not model inference. Smoke configuration identified its synthetic
baseline as `14420ce`; it is not a production release-provenance record. No NVDA/manual screen-reader,
manuscript-build, production-deployment, or installation-specific upgrade verification is claimed.
Scientific definitions, accepted ADRs, historical artifacts, and reset/retention policy were unchanged.
Owned preference/game settings were restored; the isolated workflow database/Redis prefix and worker
were cleaned. Temporary smoke scripts/state and the owned browser, API, frontend, PostgreSQL, and Redis
services were removed/stopped; the user's development stack was not touched. Dated synthetic evidence
remains in the local verification cache. This record does not close the separate RG-17
publication-verification requirement.
