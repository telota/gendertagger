# Wiki-Gendersort compatible implementation

## Purpose and scope

Replace the copied name-cleaning and assignment routines with an implementation developed from this
observable-behavior contract. The scientific method remains
[Wiki-Gendersort](https://github.com/nicolasberube/Wiki-Gendersort), with the project's existing
forename-token consensus and `wiki_gendersort_v1` normalization. This specification and
[ADR-0045](decisions/ADR-0045-wiki-gendersort-compatible-implementation.md) supersede the verbatim-port
implementation choice in ADR-0013; immutable SQLite provisioning in ADR-0023 remains in effect.

The replacement changes implementation identity to `wiki_gendersort_v2`, while keeping the method name,
normalization version, lookup schema/compiler versions, configuration, and prediction evidence contract.
It does not rebuild the table, change canonical labels, or define a different aggregation strategy.
Existing predictions remain immutable. Scheduled executions retain their recorded implementation identity;
operators must finish old executions with their matching worker version before replacing those workers.

## Pure rule interface

The module `gendertagger.methods.wiki_gendersort_rules` provides two typed operations:

- `clean_candidates(name, transliterate)` returns ordered candidate strings, retaining duplicates.
- `resolve_candidates(name, candidates, native_labels)` returns the native label and matched candidate.

`transliterate` is a deterministic string-to-string function; production uses the locked `unidecode`
dependency. Tests may inject a function with the same contract. The rule module performs no filesystem,
database, network, or model access. It owns no persistent cache or user-specific state.

## Candidate generation

### Character definitions

A counted letter is one source character whose individual transliteration is exactly one ASCII letter
from `A` through `Z` or `a` through `z`. Unicode `isalpha()` is not an equivalent predicate. For example,
`É` is retained, whereas `Æ` and `ß` expand to multiple letters and act as delimiters. Thus `Ægir`
produces `Gir` and `ßara` produces `Ara`.

A counted vowel is a character whose individual transliteration is contained in `aeiouyAEIOUY`. The
letter test and vowel test are separate. Character properties apply before candidate case normalization.

### Qualifier ordering

Paired double-quoted text and parenthetical text have lower priority than surrounding text. Repeatedly
relocate one enclosed span to the end, inserting spaces at the removed span and before the appended text.
A quote span extends from the first double quote to the next double quote. A parenthetical span extends
from the first opening parenthesis to the last closing parenthesis, provided opening precedes closing.
When both kinds of span are available, the parenthetical span takes priority. Remove the selected outer
delimiters; process any remaining or nested spans again. Unpaired delimiters remain until tokenization.

This ordering also applies to empty spans and mixed/nested delimiters. It is observable: candidate order
can select a different table match. Quoted or parenthetical qualifiers must not simply be discarded.

### Token and abbreviation order

After qualifier relocation, retain counted letters, ASCII periods, and ASCII hyphens. Every other
character separates tokens; Unicode dashes and combining marks are separators. Split on whitespace and
retain only tokens containing at least one counted letter.

Resolve trailing abbreviations before splitting remaining periods:

- A token of at least four source characters ending in a period is a fused trailing initial when the
  character before the period is uppercase and the character before that is lowercase. Split its last
  letter and period from the prefix; the initial immediately follows the prefix in processing order.
- A token ending in a period with a total length of two or three source characters is deferred to the
  end of the token sequence after removing one trailing period. Deferred tokens are processed in turn;
  repeated trailing periods can therefore cause another deferral. Relative order of deferrals matters.
- After deferrals, split all remaining periods, preserving component order. Empty components are allowed
  at this stage and are filtered by the final acceptance rule.

For example, `Ma. Anna` produces candidates `Anna`, `Ma`, whereas `AnnaM.` produces only `Anna` after
the single-letter initial is rejected. Fused-initial detection uses the source characters' case, not
ASCII transliteration or normalized case.

### Compound expansion and acceptance

Remove leading and trailing ASCII hyphens from each period component. If an internal hyphen remains,
consider the full compound first, followed immediately by its hyphen-separated components in order.
Components produced by repeated hyphens may be empty. Retain duplicates: `Anna-Anna` produces the full
compound and both occurrences of `Anna`.

A candidate is usable only when it contains more than one counted letter and at least one counted vowel.
Normalize a surviving candidate by uppercasing its first source character and lowercasing the rest. A
one-character candidate, if accepted by an injected transliterator, is uppercased as a whole. Emit the
normalized spelling first. If transliteration of that whole normalized spelling differs, immediately
emit the transliteration as another candidate without additional case normalization or filtering.

Examples under the locked `unidecode` dependency:

| Input | Ordered candidates |
|---|---|
| `Anna` | `Anna` |
| `J.` | none |
| `Jean-Paul` | `Jean-paul`, `Jean`, `Paul` |
| `Élise` | `Élise`, `Elise` |
| `Łukasz` | `Łukasz`, `Lukasz` |
| `Anna-Anna` | `Anna-anna`, `Anna`, `Anna` |
| `Ma. Anna` | `Anna`, `Ma` |
| `Ægir` | `Gir` |

## Ordered assignment

The table mapping contains native `M`, `F`, `UNI`, `INI`, or `UNK` labels. Lookup keys and candidate strings
are compared exactly. Begin with `UNK` and no matched candidate.

Missing candidates and candidates mapped to `UNK` do not contribute a match. Keep scanning after `UNI`;
a later definitive `M`, `F`, or `INI` takes priority and selects that later candidate as the match. If
only `UNI` matches are found, return `UNI` and the first such candidate. Stop at the first definitive
match, even when a later candidate has a different definitive label.

If candidate generation yields no candidates, empty input returns `UNK`; any nonempty input returns
`INI`. Finally, if the original input uppercased is exactly `NULL`, force the label to `UNK` without
discarding any matched-candidate evidence. Do not strip whitespace for this special case.

## Adapter and batch invariants

The surrounding adapter continues to consume all usable forename tokens through the existing shared
token extractor. It maps native labels to the existing project raw labels and reduces them with the
existing consensus priority and conflict rule. It emits no `method_confidence`. Preserve `tokens`,
`native_labels`, `token_results`, and `matched_names`, including their order and multiplicity. Preserve
normalization provenance, substantive unknowns, abstention, and dependency failures.

Batch lookup retains input order, returns one result per input, and deduplicates SQL lookup keys without
deduplicating candidate evidence. Parameterized SQLite queries remain bounded at 900 keys. Lookup storage
is read-only, immutable, selected by digest, and materialized once per selected digest.

After establishing compatibility, candidate generation may be reused for identical input tokens within
one batch. Character transliteration/classification may also be reused within a bounded operation.
Caches must be scoped to that operation, respect the injected transliterator, and preserve ordered output.
Accept an optimization only after output comparison and a repeatable timing measurement. No wall-clock
threshold belongs in an ordinary test.

The delivered implementation reuses candidate lists for each distinct raw token within `assign_many`
and stores at most 256 character-property pairs within each `clean_candidates` call. Whole-candidate
transliteration remains separate. Neither cache persists between calls or selected lookup tables.

## Verification and development provenance

Keep the old comparison implementation outside the repository and all published artifacts. Commit only
synthetic expected-output tests, generated-input properties, the replacement, and documentation. Frozen
expected outputs are not regenerated during tests. Compare exact candidate lists, native labels, matched
names, raw evidence, and final predictions; matching final labels alone is insufficient.

The baseline adapter was frozen outside the repository before implementation. Specification and
characterization work have examined the old source. The replacement implementer works from this behavioral
specification in a separate agent context and reports no prior access to the old adapter, private oracle,
or upstream source. The session's agent-thread limit required reusing an earlier authentication-review
agent; its reported earlier exposure was limited to registration names, directory listings, general
architecture documents, and running tests without inspecting this method's source. It must not inspect
the excluded source during implementation. Record the actual development process and comparison results
rather than describing the whole review as a clean-room exercise or a legal clearance.

Run a deterministic generated-input comparison and, when the original source inputs and exact table are
locally available, rerun all 8,277 reference records. Record hashes and environment versions, counts,
comparison boundaries, and benchmark workload sizes without publishing personal names or source data.
Run the locked repository quality gates and inspect the built wheel and source distribution.

Replacing the current routines does not clear historical copies or grant rights to `NamesOut.txt` or its
compiled derivative. Those publication decisions remain part of RG-04 in `RELEASE_GAPS.md`.

## Verification record

The replacement and its optimizations were compared on 2026-10-03 with the frozen adapter from working
tree base `c9e3953ca97b8208de386ea3f7ac1042cb3779c1`. Both the initial replacement and the optimized
implementation passed the structured comparisons. The optimized implementation also passed raw-character
fuzzing. The original lookup compiled to 694,376 normalized unique entries from 694,410 source lines.

| Comparison | Cases | Mismatches |
|---|---:|---:|
| Structured ordered candidate lists | 40,000 | 0 |
| Raw-character ordered candidate lists | 50,000 | 0 |
| Ordered resolutions over five rotating native-label maps | 450,000 | 0 |
| Synthetic SQLite assignments | 200,000 | 0 |
| Complete synthetic predictions | 10,000 | 0 |
| Study token candidates and native/matched assignments | 11,970 | 0 |
| Complete study predictions, including raw evidence and normalization metadata | 8,277 | 0 |

The frozen adapter first reproduced every legacy CSV output field for all 8,277 study records, with no
missing identifiers or forename discrepancies. The replacement's complete predictions matched that
baseline exactly; implementation identity is recorded separately in the method descriptor. The committed
synthetic suite adds 113 cases, including cache isolation and input ordering; all 128 combined method
tests passed. These comparisons establish equivalence on the tested inputs, not a proof for every string.

### Inputs and environment

The source data and copied comparison oracle remain outside the new committed fixtures. Identifiers,
names, notes, source records, and original source code are not reproduced in this verification record.

| Input | SHA-256 |
|---|---|
| Frozen adapter | `890e288ba6090ad00cd6ddb77163b640ac9787221163e4b8ccc00d835ea23872` |
| Study input CSV | `f86c4bc35f4ae4de198c1cc749ecf1f39c059aa609e448f3c76f1338925fb3eb` |
| Original study result CSV | `40a0a3740d5910bc038e72fd64fa71b2b967db1d2543f422bb89730e10a668db` |
| Original `NamesOut.txt` | `5ea927e4e2e9f78a2bbf42669c65fe192b35ea5a0a28a199648b52066d15c861` |
| Optimized rules module | `56bfd1038bdfd89020cc8c0a3793854ff33089155f7b7ec7961372944e81b37a` |
| Replacement adapter | `f8b0f0c8768471da6a83e2cf14b2b2e9fc9720dcd89ccb8932fdfbc2397560c1` |
| Complete study prediction output | `de4aefe4784ead46ae963575b0f5363b09c2170e855e7cdf61213720727c86fd` |
| Locked Python environment | `2a07ac7e58c912fa7d098923203c4fb1b5e799a1bd0ce5d4e998faefecf92124` |

Runtime: Python 3.11.15, Unidecode 1.4.0, Pydantic 2.13.4, SQLite 3.53.1, Linux x86-64. Structured
generation used seed `2026100301`; raw-character fuzzing used seed `2026100302` and strings up to 90
characters with overlapping delimiters, Unicode variants, combining marks, control characters, and emoji.
The session-local scripts and JSON reports, including individual timings and input/output digests, are
under `/tmp/gendertagger-wiki-reimplementation/`; preserve approved evidence before publication.

### Measured optimization

Seven paired rounds alternated reference/replacement execution order in the same process after one
untimed warmup. Timing used `perf_counter`, with garbage collection collected before and disabled during
each round. Every timed result was checked for equality. Imports and lookup compilation are excluded.

| Batch workload | Tokens / distinct inputs | Reference median | Replacement median | Observed speedup |
|---|---:|---:|---:|---:|
| Distinct synthetic names | 6,000 / 6,000 | 123.885 ms | 62.600 ms | 1.98x |
| Repeated synthetic names | 6,000 / 10 | 78.493 ms | 2.136 ms | 36.74x |
| Study corpus tokens | 11,970 / 1,401 | 117.175 ms | 14.620 ms | 8.01x |

These are local measurements of `assign_many`, not end-to-end application latency guarantees. Individual
rounds show scheduler noise; raw samples and minimum/maximum ranges are recorded with the reports. The
study result especially benefits from repeated-token reuse. Candidate cleaning measured separately was
3.45x faster for distinct inputs, 1.59x for repeated inputs, and 2.18x for the study tokens.

### Engineering checks

The current working tree passed the locked backend handoff checks. These results cover this implementation
increment; they do not replace the future fixed-publication-commit verification required by RG-17.

| Check | Result |
|---|---|
| Lock consistency, documentation, contract naming, package initializers, dead-code policy | Passed |
| Ruff format/lint, strict mypy, complementary Pyright, six import-boundary contracts | Passed |
| Python and backend npm vulnerability audits | No known vulnerabilities reported |
| Fast pytest profile | 1,680 passed |
| PostgreSQL pytest profile | 280 passed |
| Redis pytest profile | 7 passed |
| Combined backend branch-aware coverage | 87.59%; required scientific modules 100% |
| Replacement rules module branch-aware coverage | 100% |
| Disposable-database Alembic upgrade and schema check | Passed |
| Locked offline wheel/sdist build and distribution policy | Passed |
| Packaged adapter, rules, and sdist method tests | Byte-identical to the verified source |
| OpenAPI snapshot tests and frontend transport drift check | Passed |

The service tests removed their disposable databases and left dedicated Redis database 15 empty. Built
artifacts, checksums, JUnit, combined coverage, and service/build evidence remain in the session-local
verification directory. The old oracle and study assets were not included in either Python archive.
