# ADR-0023: Content-addressed SQLite method lookup assets

**Status:** Accepted

## Context

Wiki-Gendersort, HIVOTO, and GND depend on external datasets that are too large, separately licensed, or
updated independently of the application. The initial Wiki-Gendersort and HIVOTO adapters selected these
inputs by direct filesystem paths. A path does not identify file content, can differ across workers, and does
not satisfy the method-data checksum provenance required by
[provenance and reproducibility](../11-provenance-and-reproducibility.md). Their accepted decisions explicitly
deferred versioned snapshot resolution to the GND migration; see
[ADR-0013](ADR-0013-wiki-gendersort-adapter.md) and
[ADR-0018](ADR-0018-hivoto-adapter.md).

The application already stores immutable bytes in content-addressed artifact storage and exposes
`MethodExecution.data_artifact_id`, but run scheduling does not resolve or record method-data artifacts. Loading
the published 694,376-row Wiki-Gendersort table and the large HIVOTO source into a Python dictionary in every
worker process also repeats parsing and multiplies resident memory. A complete GND dump is larger still, while
putting every authority row and every retained revision in the application PostgreSQL database would burden
backups, replication, and retention. The default deployment must remain local-first under
[ADR-0005](ADR-0005-local-first-data-processing.md).

GND records also expose an entity type. The legacy ground-truth builder retained that type but its lookup script
used only gender. The canonical `gnd_v1` normalization profile already maps `organisation` to `institution`, and
the reference corpus historically includes organizations represented in a person register. Entity-type use is
therefore part of the GND authority-adapter decision and must be versioned and characterized with the reference
fixture. See [methods and aggregation](../07-methods-and-aggregation.md).

## Decision

Register original Wiki-Gendersort, HIVOTO, and GND sources as immutable source artifacts, then compile each
source once into its own immutable SQLite lookup artifact. SQLite is selected over LMDB, RocksDB, a custom
binary index, and application-PostgreSQL lookup rows because it is available through Python's standard library,
supports indexed concurrent read-only lookup, preserves typed structured GND fields, and adds no runtime
dependency. PostgreSQL stores only artifact metadata and execution provenance.

The compiled logical artifact types are `wiki_gendersort_lookup`, `hivoto_lookup`, and `gnd_lookup_snapshot`.
Each resolved method configuration contains the required `lookup_sha256` of its compiled artifact. Run
scheduling resolves the digest together with the method's required logical type and stores the exact artifact ID
on `MethodExecution.data_artifact_id`; absent or ambiguous assets fail scheduling. Workers materialize the
content-addressed artifact to a verified local path, validate its method and lookup-schema metadata, and open it
with read-only, immutable, and query-only SQLite settings. Local storage returns its existing digest path;
future remote storage may populate a host-local cache by digest. Runtime classification never downloads from an
external service.

Every lookup artifact records its method, lookup-schema version, compiler version, ordered source-artifact
references and checksums, source version, SQLite version, and record count. Multiple source files additionally
produce a deterministic source-manifest checksum inside the compiled lookup. Compilation is deterministic at
the logical-record level and inserts keys in stable order where the source fits in memory. Exact published bytes
remain authoritative through their artifact checksums. The compiled derivative inherits its sources' license
and access restrictions. The `MethodExecution` references the compiled artifact actually consumed; its metadata
links back to every source checksum and the compiler version.

Wiki-Gendersort compilation preserves the published `NamesOut.txt` key and native label; the adapter still runs
the frozen `nameclean` behavior at prediction time. HIVOTO compilation performs the frozen spelling expansion,
gender mapping, majority vote, priority tie break, and certainty reduction once, preserving the existing
adapter output. Both adapters bulk-resolve all candidate keys in a task batch. This supersedes their provisional
`names_db_path` and `dataset_path` configuration without changing normalization.

The GND v1 builder accepts one or more locally acquired DNB MARC21-XML entity dumps, optionally
gzip-compressed, and emits a minimal lookup keyed by GND ID. A complete classification snapshot must include at
least the DNB person and corporate-body entities; the CLI accepts all files from one dated release and records
each source separately. The builder derives the normalized entity family from the authoritative heading field,
while preserving detailed `075 $b` and legacy `079 $b/$v` entity codes. It preserves the exact `375 $a` source
gender value, maps ISO 5218 `1`/`2` and textual male/female values to a stable lookup label, and retains the
gender URI, preferred name, and source record status. The adapter applies this order:

1. no input GND ID or no row in the selected snapshot returns `no_gnd` and abstains;
2. a corporate-body entity returns `organisation` and normalizes to `institution`;
3. a person with recognized GND gender returns the stable male or female lookup label;
4. a person without recognized gender or another retained entity type returns `Unbekannt` and normalizes to
   substantive `unknown`.

Raw source fields and the resolved entity type remain in `Prediction.raw_output`. Before accepting reference
compatibility, characterize entity-type classification against the preserved corpus; a difference from the
published output requires a new adapter implementation version even though the existing normalization mapping
already supports `organisation`.

HIVOTO acquisition is manual because its RADAR dataset requires an interactive license acceptance. The CLI
registers the user-supplied file but never bypasses that gate. Wiki-Gendersort may be acquired from an explicit
HTTPS source pinned by expected checksum or registered from a checked-out repository. GND full dumps are
acquired separately from DNB and compiled locally. OAI or weekly GND changes must produce a new immutable
snapshot; published artifacts are never updated in place.

Transformer, local-LLM, and XGBoost methods use the same content-addressed materialization and provenance
boundary where applicable, but retain their native model formats. SQLite is only the compiled lookup format for
table-backed methods.

## Consequences

- A resolved run identifies the exact lookup bytes rather than a host-specific path, and workers fail loudly
  when those bytes are unavailable or corrupt.
- The application database remains small; retained GND revisions live in artifact storage and can be removed
  only under a retention policy that respects referencing runs.
- Wiki-Gendersort and HIVOTO no longer parse large source files in every worker process; their scientific
  compilation becomes an explicit, versioned provisioning step.
- GND entity types can distinguish corporate bodies from people while preserving source labels and type
  provenance.
- SQLite lookup reads must be batched and measured under deployment concurrency. Performance measurement is a
  verification gate, not a backend-selection mechanism; changing the physical format later requires a new
  lookup-schema version and ADR.
- The v1 GND builder deliberately supports MARC21-XML only so the core service adds no RDF parser dependency.
  RDF and incremental-change input adapters may be added later without changing the GND prediction contract.
