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
| RG-02 | P1 | Private frontend caches survive account replacement | Open; reproduced in mounted app |
| RG-03 | P1 | Research data and personal metadata need publication clearance | Decision needed |
| RG-04 | P1 | Wiki-Gendersort publication rights and replacement provenance | Replacement verified; history/data decisions remain |
| RG-05 | P1 | HIVOTO-trained model lacks an explicit redistribution/licensing decision | Decision needed |
| RG-06 | P1 | Manuscript reports the wrong NQG threshold | Open |
| RG-07 | P2 | Method reference contradicts implemented contracts | Fixed; GND entity-type precedence restored |
| RG-08 | P2 | Project workers accept outputs under stale execution provenance | Open; reproduced |
| RG-09 | P2 | Technical classification errors remain cached after recovery | Open; reproduced |
| RG-10 | P2 | CSV analysis exports preserve spreadsheet-active values | Open; reproduced |
| RG-11 | P2 | Quickstart omits required team bootstrap and roster membership | Open |
| RG-12 | P2 | Artifact detail screens do not validate route ownership | Open; reproduced |
| RG-13 | P2 | Delivery documents overstate release and migration verification | Open |
| RG-14 | P3 | Progress counts remain zero until an entire method completes | Open; reproduced |
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

**Evidence.** [BatchExecutor](backend/src/gendertagger/services/execution.py) resolves the current
registry adapter and validates against its current descriptor, without comparing the persisted method
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

### RG-09: Prevent technical error results from poisoning classification caches

**Evidence.** [DirectClassificationService](backend/src/gendertagger/services/classification.py) caches
all predictions, including technical errors, without expiry. A fail-once adapter returned an error for
the same name twice with one adapter call; another name succeeded after recovery. Cached failures can
affect both direct requests and public jobs using this service.

**Plan.** Exclude technical errors from the result cache, or define a short bounded error lifetime with
an injected clock. Keep cache identity consistent with the method/configuration/artifact revisions that
determine output. Preserve the normal distinction between a substantive unknown and an execution error.

**Closure.** A transient failure followed by recovery retries the same name and returns fresh output.
Successful cache hits remain effective, and concurrent calls/eviction do not corrupt results. Do not
mutate previously persisted immutable job outputs as part of cache recovery.

### RG-10: Make analysis downloads safe for spreadsheet use

**Evidence.** The JSON/tabular path accepts identifiers such as `=1+1`;
[the CSV serializer](backend/src/gendertagger/export/csv_analysis.py) emits them verbatim. CSV quoting
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

**Evidence.** [ExportDetailView](frontend/src/features/export/ExportDetailView.vue) fetches an export
without validating its relationship to route project/run IDs, then builds aggregation links from those
IDs. A reproduction opened an export beneath an unrelated project/run and produced the wrong link.
[EvaluationDetailView](frontend/src/features/evaluation/EvaluationDetailView.vue) and
[AggregationDetailView](frontend/src/features/runs/AggregationDetailView.vue) have equivalent gaps.
Server authorization still applies; this finding concerns inconsistent client context, not a confirmed
server authorization bypass.

**Plan.** Resolve and validate resource-to-run-to-snapshot-to-project ownership using canonical API
responses before rendering detail content or links. Prefer an existing shared route-context pattern.
Fail closed for mismatches and stale navigation; keep business rules in the API rather than introducing
page-specific backend endpoints.

**Closure.** Test mismatched project/run/resource IDs, direct refreshes, rapid route changes, and correct
deep links for all three screens. No artifact or evidence is presented under an unrelated context.

### RG-13: Align delivery claims with implemented and verified operations

**Evidence.** [The implementation plan](docs/15-implementation-plan.md#phase-7-deployment-hardening)
marks protected tagged publication and previous-release migration rehearsal complete.
[Engineering policy](docs/18-engineering-and-quality.md) and
[the production runbook](docs/21-production-promotion.md) describe commit-based publication, deferred
versioned-release automation, and a migration helper that does not establish a previous schema or expose
the readiness endpoint it probes. [The frontend overview](frontend/README.md) also understates delivered
screens.

**Plan.** Distinguish implemented capability, completed verification, and deferred automation. Correct
the roadmap/overviews immediately. Choose a documented manual or automated release process for the
publication scope. Before claiming upgrade readiness, rehearse target migrations against an isolated
copy of the actual previous schema/data and verify startup, restore, and rollback. Repair or retire
[the misleading helper](deploy/scripts/test_migration.sh).

**Closure.** Documentation agrees with CI and operational commands. A retained rehearsal record names
previous/target versions, images, database state, backup/restore checks, and smoke-test results. Where no
previous release exists, record fresh-install evidence and the upgrade limitation explicitly.

### RG-14: Refresh progress after every terminal batch

**Evidence.** [Execution finalization](backend/src/gendertagger/db/repositories/run_repository.py)
returns while any batch is outstanding before refreshing execution tallies. With one completed
200-record batch and another pending batch in a 400-record execution, progress stayed zero. Run GET and
SSE inherit these counts.

**Plan.** Refresh tallies independently of the terminal-state decision, under the existing concurrency
protection, and aggregate run progress consistently. Preserve definitions of completed/failed counts
and the separation between success, abstention, and technical errors.

**Closure.** Multi-batch and concurrent-worker tests show accurate intermediate counts, identical
GET/SSE state, no duplicate counting, and unchanged final lifecycle transitions.

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
| 2 | Fix credential concurrency and private account state: RG-01, RG-02 | Add deterministic PostgreSQL and mounted-app regressions; preserve API/session and principal boundaries |
| 3 | Correct manuscript and method documentation: RG-06, RG-07 | Ground prose in study artifacts and accepted contracts; preserve approved scientific outputs |
| 4 | Harden worker provenance and caches: RG-08, RG-09 | Define compatibility/recovery first; incompatible workers write no predictions; recovered methods retry errors |
| 5 | Repair export and navigation correctness: RG-10, RG-12, RG-15 | Design/version export changes first; retain canonical IDs, immutable outputs, and append-only review history |
| 6 | Repair setup, progress, and delivery claims: RG-11, RG-13, RG-14 | Fresh-install/browser and migration/restore evidence match the documentation |
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

**Current document-preparation recheck (2026-10-03):** both previously failing CLI tests now pass
against isolated temporary PostgreSQL databases, and Pyright reports zero errors/warnings. These
specific historical failures are resolved in the rechecked workspace; they are not current blockers.
This targeted recheck does not replace the final full suite or verify unrelated concurrent changes.
The main implementation/documentation findings were rechecked in source and remain open; the rights
findings still require recorded decisions.

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
verified procedure. The production runbook explicitly warns that the existing
[migration helper](deploy/scripts/test_migration.sh) is not evidence of a previous-to-current upgrade
rehearsal. The implementation plan nevertheless marks deployment hardening and rehearsal complete.
These operational claims and verification gaps remain RG-13 rather than becoming a new release item.

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

This supplemental review examines backend and frontend maintainability separately, followed by repository
artifacts and documentation. It used HEAD `c9e3953ca97b8208de386ea3f7ac1042cb3779c1` plus the existing local
changes. This review changed only this report; implementation, dependencies, generated contracts, tests, and
existing local work were left intact. Findings below are recommendations, not completed fixes.

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
All recommendations remain open, and scope decisions are identified explicitly below.

### Quality findings register

| ID | Priority | Area | Finding |
|---|---|---|---|
| BQ-01 | P2 | Backend | Copied diagnostic formatters have inconsistent credential redaction |
| BQ-02 | P3 | Backend | Redundant helpers and dormant recovery/authentication surfaces remain |
| BQ-03 | P2 | Backend | Worker retry policy and infrastructure construction are copied |
| BQ-04 | P3 | Backend | Three executors repeat transaction, retry, and terminal-failure policy |
| BQ-05 | P2 | Backend | Dispatch persistence repeats common intent handling and field projection |
| BQ-06 | P3 | Backend | Historical runtime snapshot/configuration compatibility can be retired |
| BQ-07 | P2 | Backend | The dead-code gate counts words rather than application reachability |
| FQ-01 | P2 | Frontend | Query keys, cursors, polling, and invalidation need shared ownership |
| FQ-02 | P2 | Frontend | Shared domain UI and helpers remain coupled to feature folders |
| FQ-03 | P2 | Frontend | Artifact interfaces duplicate canonical Pydantic contracts |
| FQ-04 | P2 | Frontend | Dialog structure and overlay styling are implemented repeatedly |
| FQ-05 | P2 | Frontend | Creation disclosure and cursor-list feedback are copied between views |
| FQ-06 | P2 | Frontend | Lifecycle, provenance, prediction, and annotation-history presentation repeat |
| FQ-07 | P2 | Frontend | Repeated native fields bypass incomplete shared field primitives |
| FQ-08 | P3 | Frontend | An orphan component, unused exported types, and dead CSS survive checks |
| DQ-01 | P2 | Documentation | Overlapping guidance and undated reports now disagree |
| DQ-02 | P2 | Documentation | The documentation gate omits maintained files and section targets |
| DQ-03 | P3 | Repository | Generated paper output and disposable development metadata are tracked |
| DQ-04 | P3 | Repository | Exact research/manuscript copies lack a deliberate archival policy |

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

### Frontend findings

#### FQ-01: Share query ownership, cursor mechanics, and list polling

**Evidence.** [Aggregation queries](frontend/src/features/runs/useAggregations.ts), line 36;
[evaluation queries](frontend/src/features/evaluation/useEvaluations.ts), line 31; and
[export queries](frontend/src/features/export/useExports.ts), line 25, repeat infinite-query setup,
cursor continuation, two-second live-item polling, and creation invalidation. Source contains 21
`initialPageParam` setup sites. Detail polling already has
[a shared composable](frontend/src/composables/usePolledQuery.ts).
Snapshot reads in `useSnapshotImport`/`useSnapshotData` and run reads in `useRunDetail`/`useTaskData`
also use different keys for equivalent resources. Principal/request ownership differs between older
run/artifact queries and newer snapshot/task/admin queries; annotation invalidation independently knows
literal cache layouts in [useAnnotate](frontend/src/features/review/useAnnotate.ts), lines 54 and 78.

**Plan.** Establish shared typed resource key/options builders, cursor helpers, and list polling.
Keep endpoint request functions, filters, and lifecycle predicates explicit. Move `currentData` out of
the project feature into shared query support. Apply one principal/cancellation convention to reads,
writes, and invalidation, using the same key definitions everywhere. This is the consolidation path
for RG-02 and supports RG-12; it does not replace those correctness fixes.

**Closure.** Cursors remain tied to their exact principal/resource/filter/sort context; late requests
cannot update a replacement account; polling and cancellation retain correct lifecycle behavior; shared
invalidation refreshes all affected projections. Preserve the account/route regression coverage.

#### FQ-02: Move already-reused domain presentation into shared modules

**Evidence.** [The coding guidelines](docs/26-frontend-coding-guidelines.md) forbid cross-feature
imports, but [VocabBadge](frontend/src/features/review/VocabBadge.vue) serves review, game, method
results, and project statistics from the review feature. [GameModeView](frontend/src/features/game/GameModeView.vue),
lines 14–31, imports person presentation, badges, names, retention logic, annotations, reads, filters,
and vocabulary from other features. Project snapshot panels import review person details; evaluation
imports review vocabulary. Shared lifecycle translation remains owned by
[runs](frontend/src/features/runs/useStatusLabel.ts).

**Plan.** Promote vocabulary badges, person details, and lifecycle presentation into the documented
`components/domain/` location. Move common token/gloss/name helpers into shared domain modules and
stateful resource reads into shared composables/query support. Keep screen orchestration in features
and make dependency direction explicit; a new barrel that preserves feature coupling is insufficient.

**Closure.** Shared presentation has no feature dependency; consumers import defining shared modules;
canonical tokens, uncertainty distinctions, translation, colors, and original source text remain intact.
Enforce the boundary or document narrow justified exceptions.

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

#### FQ-08: Remove confirmed orphan frontend code and cover unused exports

**Evidence.** [AppListbox](frontend/src/components/base/AppListbox.vue) has no application import,
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

### Verification and limits of this supplemental review

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

Installed backend check tools were Python 3.11.15 and Ruff 0.16.2. Frontend checks used Node 26.10.0,
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
