# ADR-0024: Content-addressed model manifests for the Hugging Face transformer adapters

**Status:** Accepted

## Context

The published reference ensemble includes two Hugging Face sequence-classification models over forename
tokens: `padmajabfrl/Gender-Classification` (DistilBERT) and `imranali291/genderize` (BERT-cased). Both are
distributed as several files (`config.json`, tokenizer files, one or more weight shards) rather than one
blob, unlike the SQLite lookups compiled for Wiki-Gendersort, HIVOTO, and GND under
[ADR-0023](ADR-0023-content-addressed-sqlite-method-lookups.md). ADR-0023 already commits these methods to
"the same content-addressed materialization and provenance boundary where applicable, but retain their
native model formats," without specifying a mechanism, because `ArtifactStorage` (`materialize`) addresses
exactly one byte stream per digest and cannot represent a directory.

A pinned-revision configuration (a Hugging Face repo ID plus a commit SHA, resolved through a local or
process-wide Hugging Face cache) was considered and rejected: it reproduces the exact host-local-path problem
ADR-0023 already removed for Wiki-Gendersort and HIVOTO — a resolved run would identify a model by a mutable
external reference rather than exact verified bytes, and workers could silently disagree if their caches
diverge. Packing the model directory into a single tar/zip archive and content-addressing the archive was
also considered; it was rejected because it reopens the archive-safety surface (member-count limits, path
traversal, decompression-bomb protection) already built out for snapshot-import packaging, for content that
is operator-provisioned rather than externally submitted, where that hardening buys little.

## Decision

Extend ADR-0023's mechanism instead of introducing a new one. Each constituent model file is registered as
its own content-addressed artifact through the existing `LookupAssetRegistrationService.register_file`,
unchanged. A small immutable **model manifest** artifact — its bytes are a `ModelManifestMetadata` JSON
document (`gendertagger.models.artifact`) — lists those member files in a fixed order with each member's
relative path, artifact ID, SHA-256, and byte size, together with `method_name`, `model_schema_version`,
`compiler_version`, `source_identifier` (the Hugging Face repo ID), and `source_revision` (the pinned commit
SHA the operator resolved out of band; acquisition is manual, mirroring HIVOTO's licensed-source acquisition
under ADR-0023). `relative_path` reuses `normalize_source_member_logical_name`
(`gendertagger.models.project`) unchanged, so the same forward-slash-only, no-traversal, no-control-character
validation already enforced for snapshot source members applies here.

Each resolved `hf_distilbert`/`hf_genderize` method configuration is a `LookupMethodConfig` whose
`lookup_sha256` is the manifest artifact's digest, so `MethodRegistration`, `MethodExecution.data_artifact_id`
resolution, and `MethodRegistry.resolve_run_config` require no change beyond registering the two new logical
types — the manifest artifact plays exactly the structural role the compiled SQLite lookup plays for GND,
HIVOTO, and Wiki-Gendersort.

At prediction time, a new `RegisteredModelDirectoryResolver`
(`gendertagger.services.model_assets`) resolves the manifest and each member through the existing
`LookupAssetResolver.materialize(logical_type, sha256)` — reused as-is, with no changes to
`lookup_assets.py` — then hard-links (falling back to a copy across filesystems) each verified member into a
stable directory named by the manifest's own digest, at its exact relative path, once per process. Workers
never download from an external service at prediction time; a materialized directory is loaded with
`from_pretrained(..., local_files_only=True)`. The directory cache root is a new `model_cache_root` setting,
configured the same way as `artifact_root`.

Both adapters (`gendertagger.methods.hf_distilbert`, `gendertagger.methods.hf_genderize`) follow the
name-tokenizing classifier pattern from [ADR-0012](ADR-0012-name-based-classifier-adapter-pattern.md): they
split each person's forename with the shared `usable_forename_tokens` filter, classify every usable token
independently through a lazily loaded, per-digest-cached, injectable backend, and reduce per-token labels
with `consensus_label`, exactly like `gender_guesser`, `wiki_gendersort`, `hivoto`, and `nomquamgender`. Model
inference is a batched forward pass in evaluation mode with no dropout and greedy argmax over logits, so it
is deterministic given identical weights and tokens. The two methods are separate adapter classes, not one
parameterized class, because their label-index polarity is inverted (DistilBERT: index 0 male, index 1
female; genderize: index 0 female, index 1 male, per `docs/07-methods-and-aggregation.md`) and their frozen
`hf_distilbert_v1`/`hf_genderize_v1` normalization profiles are already independent.

The `transformers` and `torch` packages are declared as a new opt-in `transformers` extra, lazily imported
only inside the adapters' backend factory, raising `MethodDependencyError` when absent — the same shape as
every other optional method dependency.

## Consequences

- A resolved run identifies exact model bytes rather than a Hugging Face repo/revision reference or a
  host-local cache entry; workers fail loudly (`MethodDependencyError`) when a manifest, a member, or the
  `transformers`/`torch` extra is unavailable or fails verification.
- Provisioning a transformer method requires the operator to first materialize a model snapshot locally (for
  example via `huggingface-cli download --revision <sha>`) and then run a new `assets prepare-hf-model` CLI
  step that registers every file and the manifest; there is no automatic download at run time, consistent
  with local-first operation under [ADR-0005](ADR-0005-local-first-data-processing.md).
- No changes were required to `ArtifactStorage`, `LocalArtifactStorage`, `lookup_assets.py`, or
  `MethodRegistration`'s validation; the manifest is exactly one more content-addressed artifact from their
  point of view.
- The materialized-directory cache is a new local resource distinct from artifact storage's own
  content-addressed tree; it is not itself content-addressed by the runtime (it is keyed by manifest digest
  and rebuilt idempotently from already-verified members), so it is safe to clear and does not require
  backup.
- HIVOTO-XGBoost (Phase 5 item 9) is expected to reuse this same manifest mechanism for its vectorizer and
  booster files rather than introducing a third approach; that adapter is out of scope for this record.
