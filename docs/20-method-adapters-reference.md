# Method adapters reference

This reference document describes the ten classification components, their adapter protocols, runtime dependencies, lookup artifacts, input fields, normalization profiles, and configuration schemas implemented in `gendertagger.methods`.

For normative pipeline behavior, voting rules, and agreement logic, see [`07-methods-and-aggregation.md`](07-methods-and-aggregation.md).

## Shared contracts and canonical labels

All classification adapters implement the `GenderMethod[MethodConfigT]` protocol defined in [`gendertagger.methods.base`](../backend/src/gendertagger/methods/base.py).

### Canonical label alphabet

Every adapter maps raw predictions onto a unified set of four canonical labels:

- `male`
- `female`
- `unknown` (substantive classification of ambiguity)
- `institution` (corporate body or organization)

A method may also report an outcome status of:

- `success`: A canonical label was resolved (including substantive `unknown`).
- `abstain`: The method declined or had no usable input (e.g. no checkable forename token, or an absent or unmatched GND ID).
- `error`: Technical failure occurred during processing.

Known ambiguity labels such as `unknown`, `andy`, and `conflict` normalize to `success` with
substantive `unknown`, not abstention. An unfamiliar spelling does not itself determine a model-based
adapter's answer. Name-based methods abstain on a final `no_name`; Wiki-Gendersort can produce this
through native `INI` even when a token survives the shared filter.

### Execution inputs and outputs

Each adapter accepts a sequence of `PersonInput` objects and a resolved `MethodConfig`. Adapters return a list of `PredictionResult` objects matching the exact length and order of the inputs.

```text
PersonInput -> Adapter (GenderMethod) -> PredictionResult
```

### Provenance and confidence

[`PredictionResult`](../backend/src/gendertagger/models/classification.py) separates `label`, `status`,
`raw_label`, `raw_output`, `metadata`, and optional `method_confidence`. Normalization preserves the
adapter's exact raw label and evidence, recording `normalization_version` and `normalization_reason`
in metadata. Missing or unparseable raw labels abstain; the explicit `error` sentinel produces
`error` with no label. Directly constructed local-LLM error results are described separately below.

The descriptor declares implementation and normalization versions independently. Scheduling records
the descriptor, resolved configuration, and selected data artifact on the MethodExecution; artifact
identifiers and source checksums are not automatically added to every prediction's metadata.

Only `local_llm` declares and reports `method_confidence`, in the inclusive range `[0, 1]`. The other
nine adapters leave it null. NQG and HIVOTO-XGBoost token probabilities remain raw evidence, not
overall method confidence. Confidence is method-specific, not globally calibrated, and does not
influence the `reference_v1` vote, agreement score, or pipeline certainty tier.

### Shared forename tokenization and consensus

Seven adapters use the frozen token filter in
[`gendertagger.methods.name_tokens`](../backend/src/gendertagger/methods/name_tokens.py). Six also use
its `consensus_label`; HIVOTO-XGBoost retains its own reduction.

`usable_forename_tokens` whitespace-splits every `person.forenames` value in source order. It skips
tokens starting with `(`, a standalone `)`, dotted one-character initials, digit-leading fragments,
ASCII-dash-only fragments, and the frozen particle/noise-word set after lowercasing and stripping
trailing punctuation for membership checks. Surviving tokens retain their original spelling and
punctuation. This is not general removal of parenthetical spans or bare single letters; historical
quirks such as surviving `Geb.` and `Jr.` are deliberately preserved.

The six shared reducers return `no_name` for no token results and `conflict` when results occur on
both sides of the adapter's male/female label sets, regardless of token counts. Those sets include
leaning labels for gender-guesser and HIVOTO. Otherwise the highest-priority label wins; this is not
a majority vote across tokens. All seven name-based adapters read only `person.forenames`, with no
surname, alternative-name, or `person.name_forms` fallback.

### Registration

[`gendertagger.services.method_registry`](../backend/src/gendertagger/services/method_registry.py) registers all
ten adapters with their descriptor, closed configuration model, routing queue, and batch size. Every
adapter routes to the `cpu` queue except `local_llm`, which routes to `llm`; the batch size is 200 for
all ten. Registrations that name a `data_artifact_logical_type` require a `LookupMethodConfig`, so run
scheduling can resolve `lookup_sha256` to a registered artifact before any batch is dispatched.

The current `llm` routing follows [the queue specification](06-task-queue.md#queues). The CPU-queue
wording in [ADR-0026](decisions/ADR-0026-local-llm-adapter.md) does not describe the current
registration. Runtime libraries are standard dependencies under
[ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md), which supersedes the earlier
per-method extras decisions; lookup artifacts, model files, and the LLM server still need provisioning.

### Configuration examples

All adapter configurations are closed Pydantic models: unknown fields are rejected. These examples
are adapter `config` objects keyed by method name, not a complete RunConfig or API request.
`lookup_sha256` must be a lowercase 64-character hexadecimal digest of the registered compiled
SQLite artifact or model manifest, not a source-file digest or filesystem path.

The repeated digest below is a schema illustration, not a provisioned artifact. Replace it
independently for each data-backed method with its registered artifact digest. Provision the named
LLM at the configured local endpoint before executing `local_llm`; configuration validation alone
does not establish asset or server availability.

```yaml
parenthetical_qualifier: {}
gnd:
  lookup_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
gender_guesser: {}
wiki_gendersort:
  lookup_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
hivoto:
  lookup_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
nomquamgender:
  threshold: 0.1
hf_distilbert:
  lookup_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
hf_genderize:
  lookup_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
local_llm:
  model: "gpt-oss:20b"
  base_url: "http://localhost:11434/v1"
  api_key: "ollama"
  system_prompt: "You are an expert archivist identifying the gender of historical persons."
  temperature: 0.0
  max_validation_retries: 2
hivoto_xgboost:
  lookup_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
```

## Implemented method adapters

The pipeline contains ten components across five methodological families. Nine components participate in the reference ensemble (`reference_v1`), while HIVOTO-XGBoost is an experimental component.

### 1. Parenthetical Qualifier (`parenthetical_qualifier`)

- **Module**: [`gendertagger.methods.adapters.parenthetical_qualifier`](../backend/src/gendertagger/methods/adapters/parenthetical_qualifier.py)
- **ADR**: [ADR-0010](decisions/ADR-0010-parenthetical-qualifier-adapter.md), [ADR-0014](decisions/ADR-0014-restore-parenthetical-institution-normalization.md)
- **Role**: Authority override rule (highest priority in ensemble).
- **Dependencies**: Built-in standard library (regular expressions).
- **Configuration**: `ParentheticalQualifierConfig`, an empty closed model; no parameters are accepted.
- **Normalization Profile**: `parenthetical_qualifier_v1`.
- **Implementation Version**: `parenthetical_qualifier_v1`.
- **Inputs Consumed**: `person.surname`, `person.forenames`, then `person.note`.
- **Behavior**: Scans parenthesized content in the surname and each forename for a relational keyword, preferring the leading word of the parenthesis and falling back to any word in it. Female kinship terms (`Frau`, `Tochter`, `Witwe`, ...) map to `female`, male ones (`Herr`, `Sohn`, `Bruder`, ...) to `male`, family-group terms (`Familie`, `Kinder`, `Geschwister`, `Ehepaar`, ...) to substantive `unknown`, and commercial/organisational terms (`Firma`, `Weinhandlung`, `Bankier`, `Kaufleute`) to `institution`. If no name field matches, the note is consulted, but only on its first word and never for `institution`. With no match the adapter emits no raw label at all and normalizes to `abstain`.
- **Evidence**: A match preserves `matched_keyword` and `matched_field` (`surname`, `forename`, or
  `note`) in raw output. No match retains `raw_label=null` and empty raw output, with normalization
  reason `missing_raw_label`. ADR-0014 supersedes ADR-0010's former institution-as-abstention behavior.

### 2. GND Local Snapshot (`gnd`)

- **Module**: [`gendertagger.methods.adapters.gnd`](../backend/src/gendertagger/methods/adapters/gnd.py), which defines the
  runtime `GndMethod` adapter registered under the method name `gnd`. The separate offline compiler
  [`gendertagger.methods.gnd_snapshot`](../backend/src/gendertagger/methods/gnd_snapshot.py) turns DNB
  MARC21-XML full dumps into the immutable SQLite lookup this adapter reads; it is not itself a
  classification method.
- **ADR**: [ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md), [ADR-0046](decisions/ADR-0046-gnd-entity-type-precedence.md)
- **Role**: Authority override lookup (second priority in ensemble).
- **Dependencies**: Built-in `sqlite3` for lookup; the shared snapshot module also imports the standard
  backend dependency `lxml` used for offline MARC21-XML compilation.
- **Configuration**: `GndConfig`, a `LookupMethodConfig` requiring `lookup_sha256` for a compiled
  `gnd_lookup_snapshot` SQLite artifact.
- **Normalization Profile**: `gnd_v1`.
- **Implementation Version**: `gnd_v2`; normalization and compiled lookup identities remain unchanged.
- **Inputs Consumed**: `person.gnd_id`.
- **Behavior**: Bulk-resolves GND identifiers against the selected local snapshot. A missing ID or
  absent row emits `no_gnd` and abstains. Entity type takes precedence over gender: a corporate-body
  row emits `organisation`, normalized to `institution`; only a person row uses the compiled lookup
  label (`Männlich` -> `male`, `Weiblich` -> `female`, `Unbekannt` -> substantive `unknown`).
  Every other entity type emits `Unbekannt` and returns `success + unknown`, even when its source
  gender is recognized. The offline compiler, not the runtime adapter, interprets source gender codes.
- **Evidence**: Raw output preserves `gnd_id` and `lookup_match`; matched rows also preserve
  `entity_type`, `raw_entity_types`, `gender_uri`, `source_gender_label`, `preferred_name`, and
  `record_status`. Source gender remains available even when entity-type precedence yields unknown;
  it is separate from the adapter's raw classification label. Existing snapshots and predictions
  are not rewritten by the v2 correction.

### 3. gender-guesser (`gender_guesser`)

- **Module**: [`gendertagger.methods.adapters.gender_guesser`](../backend/src/gendertagger/methods/adapters/gender_guesser.py)
- **ADR**: [ADR-0012](decisions/ADR-0012-name-based-classifier-adapter-pattern.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Standard dependency (`gender-guesser`).
- **Configuration**: `GenderGuesserConfig`, an empty closed model; no parameters are accepted.
- **Normalization Profile**: `gender_guesser_v1`.
- **Implementation Version**: `gender_guesser_v1`.
- **Inputs Consumed**: All usable tokens from `person.forenames` only.
- **Behavior**: Looks up every token with a case-insensitive `gender_guesser` detector, then applies
  shared priority consensus. Priority is `no_name < unknown < andy < mostly_male < mostly_female <
  male < female`, with opposite male/female sides, including leaning labels, producing `conflict`
  first. Plain and `mostly_*` labels map to their canonical gender; `andy`, `conflict`, and dictionary
  `unknown` are successful substantive `unknown`. No usable tokens yields `no_name` and abstention.
- **Evidence**: Raw output preserves ordered `tokens` and `token_results`.

### 4. Wiki-Gendersort (`wiki_gendersort`)

- **Module**: [`gendertagger.methods.adapters.wiki_gendersort`](../backend/src/gendertagger/methods/adapters/wiki_gendersort.py)
- **ADR**: [ADR-0045](decisions/ADR-0045-wiki-gendersort-compatible-implementation.md), [ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Built-in `sqlite3` and standard dependency `unidecode`.
- **Configuration**: `WikiGendersortConfig`, a `LookupMethodConfig` requiring `lookup_sha256` for a
  compiled `wiki_gendersort_lookup` SQLite artifact.
- **Normalization Profile**: `wiki_gendersort_v1`.
- **Implementation Version**: `wiki_gendersort_v2`; replacement rules follow [the behavior specification](29-wiki-gendersort-compatibility.md).
- **Inputs Consumed**: All usable tokens from `person.forenames` only.
- **Behavior**: Generates ordered compatible candidates per token and resolves them against the
  immutable SQLite table under the linked behavior specification. Native assignment retains the
  first `UNI` fallback and stops at the first `M`, `F`, or `INI` match. Usable candidates absent
  from the table yield `UNK`; a nonempty token with no usable candidates yields `INI`. Native labels become
  project raw labels before shared consensus: `M` -> `male`, `F` -> `female`, `UNI` -> `unisex`,
  `UNK` -> `unknown`, `INI` -> `no_name`. Male/female disagreement produces `conflict`; otherwise
  priority is `no_name < unknown < unisex < male < female`. `INI` contributes a no-name result
  without suppressing stronger results from other tokens; only the final `no_name` abstains.
- **Evidence**: Raw output preserves ordered `tokens`, `native_labels`, `token_results`, and
  `matched_names`, with an empty string for an absent match. `raw_label` is the reduced project
  label, not a native table label. No logits, probabilities, or method confidence are emitted.

### 5. HIVOTO (`hivoto`)

- **Module**: [`gendertagger.methods.adapters.hivoto`](../backend/src/gendertagger/methods/adapters/hivoto.py)
- **ADR**: [ADR-0018](decisions/ADR-0018-hivoto-adapter.md), [ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Built-in `sqlite3`.
- **Configuration**: `HivotoConfig`, a `LookupMethodConfig` requiring `lookup_sha256` for a compiled
  `hivoto_lookup` SQLite artifact.
- **Normalization Profile**: `hivoto_v1`.
- **Implementation Version**: `hivoto_v1`.
- **Inputs Consumed**: All usable tokens from `person.forenames` only.
- **Behavior**: Offline compilation expands source spellings and selects each lookup key's label
  by majority with the frozen priority tie break. Runtime bulk-looks up every surviving token
  after lowercasing and stripping trailing punctuation; a miss contributes `unknown` with empty
  certainty. Person-level reduction is shared priority consensus, not majority voting:
  `no_name < unknown < andy < mostly_male < mostly_female < male < female`. Opposite male/female
  sides, including leaning labels, produce `conflict` first. Plain and `mostly_*` labels map to
  their canonical gender; `unknown`, `andy`, and `conflict` are substantive unknowns. No usable
  tokens yields `no_name` and abstention.
- **Evidence**: Raw output preserves ordered `tokens`, `token_results`, and `certainties`.
  Compiled certainty is `sicher` only when every contributing source certainty is `sicher`,
  otherwise `mittlere Sicherheit`; it neither weights consensus nor becomes method confidence.

### 6. nomquamgender (`nomquamgender`)

- **Module**: [`gendertagger.methods.adapters.nomquamgender`](../backend/src/gendertagger/methods/adapters/nomquamgender.py)
- **ADR**: [ADR-0019](decisions/ADR-0019-nomquamgender-adapter.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Standard dependency (`nomquamgender`).
- **Configuration**: `NomquamgenderConfig` with optional finite `threshold`, default `0.1`,
  constrained to `0 < threshold < 0.5`.
- **Normalization Profile**: `nomquamgender_v1`.
- **Implementation Version**: `nomquamgender_v1`.
- **Inputs Consumed**: All usable tokens from `person.forenames` only.
- **Behavior**: Annotates each token to obtain female probability `p(gf)`. A value
  `p(gf) <= threshold` is `male`, `p(gf) >= 1 - threshold` is `female`, and the intervening band
  is `uncertain`; a missing or NaN probability is `unknown`. Shared consensus uses
  `no_name < unknown < uncertain < male < female`, with male/female conflict detection first.
  Raw `unknown`, `uncertain`, and `conflict` normalize to successful substantive `unknown`.
  No usable tokens yields `no_name` and abstention, not an unrecognized-name abstention.
- **Evidence**: Raw output preserves ordered `tokens`, `pgf`, and `token_results`; missing/NaN
  probabilities are retained as null. No `method_confidence` is emitted.

### 7. Hugging Face DistilBERT (`hf_distilbert`)

- **Module**: [`gendertagger.methods.adapters.hf_distilbert`](../backend/src/gendertagger/methods/adapters/hf_distilbert.py)
- **ADR**: [ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Standard dependencies (`transformers`, `torch`).
- **Configuration**: `HfDistilbertConfig`, a `LookupMethodConfig` requiring `lookup_sha256` digest of the content-addressed model manifest.
- **Normalization Profile**: `hf_distilbert_v1`.
- **Implementation Version**: `hf_distilbert_v1`.
- **Inputs Consumed**: All usable tokens from `person.forenames` only.
- **Behavior**: Loads the selected local tokenizer/model manifest; the reference model is
  `padmajabfrl/Gender-Classification`. Evaluation-mode, no-grad inference returns argmax indices:
  `0` -> `male`, `1` -> `female`. Shared consensus returns `conflict` for mixed male/female tokens,
  normalized to substantive `unknown`; no usable tokens yields `no_name` and abstention.
- **Evidence**: Raw output preserves ordered `tokens` and mapped string `token_results`, not
  indices, logits, or softmax probabilities. `method_confidence` is null. Runtime does not download
  a model by repository name; `lookup_sha256` selects the provisioned manifest.

### 8. Hugging Face BERT genderize (`hf_genderize`)

- **Module**: [`gendertagger.methods.adapters.hf_genderize`](../backend/src/gendertagger/methods/adapters/hf_genderize.py)
- **ADR**: [ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Standard dependencies (`transformers`, `torch`).
- **Configuration**: `HfGenderizeConfig`, a `LookupMethodConfig` requiring `lookup_sha256` digest of the content-addressed model manifest.
- **Normalization Profile**: `hf_genderize_v1`.
- **Implementation Version**: `hf_genderize_v1`.
- **Inputs Consumed**: All usable tokens from `person.forenames` only.
- **Behavior**: Loads the selected local tokenizer/model manifest; the reference model is
  `imranali291/genderize`. Evaluation-mode, no-grad inference returns argmax indices with polarity
  inverted relative to DistilBERT: `0` -> `female`, `1` -> `male`. Shared consensus returns
  `conflict` for mixed male/female tokens, normalized to substantive `unknown`; no usable tokens
  yields `no_name` and abstention.
- **Evidence**: Raw output preserves ordered `tokens` and mapped string `token_results`, not
  indices, logits, or softmax probabilities. `method_confidence` is null. Runtime does not download
  a model by repository name; `lookup_sha256` selects the provisioned manifest.

### 9. Local LLM (`local_llm`)

- **Module**: [`gendertagger.methods.adapters.local_llm`](../backend/src/gendertagger/methods/adapters/local_llm.py)
- **ADR**: [ADR-0026](decisions/ADR-0026-local-llm-adapter.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Standard dependency (`httpx2`).
- **Configuration**: `LocalLlmConfig` requires `model` and `base_url`. Optional fields are
  `api_key` (default `"ollama"`), nullable `system_prompt` (default shown in the configuration
  example), `temperature` (default `0.0`), and `max_validation_retries` (default `2`).
- **Normalization Profile**: `local_llm_v1`.
- **Implementation Version**: `local_llm_v1`.
- **Inputs Consumed**: A textual projection of the complete record: `tei_id`, names, life dates,
  note, events, GND ID, and external identifiers. Captured `name_forms` take precedence over the
  legacy forenames/surname/`alt_names` projection.
- **Behavior**: Posts to `<base_url>/chat/completions` on the configured OpenAI-compatible local
  server. Requests strict JSON-schema output and validates it with `PersonClassification`, requiring
  `gender` (`female`, `male`, `institution`, or `unknown`), numeric `confidence`, and `certainty`
  (`high`, `low`, or `uncertain`), with optional `reasoning`. Only structured-content Pydantic
  validation failures receive semantic retries; the default allows three total attempts.
  `organisation` is supported by the normalization profile but rejected by the response model.
- **Evidence and Confidence**: Successful results preserve the final completion response and
  nonempty reasoning in raw output. Metadata records `model`, slash-trimmed `base_url`,
  `temperature`, `schema_name`, `attempt_count`, `self_reported_certainty`, and, after a failed
  validation attempt, `last_failed_text`, plus normalization provenance. Response confidence
  becomes `method_confidence`; batch validation enforces the declared `[0, 1]` range.
  Self-reported certainty is not the pipeline certainty tier and does not calibrate confidence.
- **Failure Boundary**: Caught record-level transport, parsing, or validation failures yield
  `error` with no label or confidence, `raw_output={"error": ...}`, and empty metadata.
  Finite confidence outside `[0, 1]` passes the response model but fails final batch contract
  validation; it is not semantic-retried or converted to a record-level error.

### 10. HIVOTO-XGBoost (`hivoto_xgboost`) [Experimental]

- **Module**: [`gendertagger.methods.adapters.hivoto_xgboost`](../backend/src/gendertagger/methods/adapters/hivoto_xgboost.py)
- **ADR**: [ADR-0025](decisions/ADR-0025-hivoto-xgboost-adapter.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Experimental component (held out from `reference_v1` voting ensemble).
- **Dependencies**: Standard dependencies (`scikit-learn`, `xgboost`).
- **Configuration**: `HivotoXgboostConfig`, a `LookupMethodConfig` requiring `lookup_sha256` for a
  `hivoto_xgboost_model_manifest`.
- **Normalization Profile**: `hivoto_xgboost_v1`.
- **Implementation Version**: `hivoto_xgboost_v1`.
- **Inputs Consumed**: All usable tokens from `person.forenames` only.
- **Artifact Contents**: `hivoto_lookup.sqlite3`, `vocabulary.json`, `idf.json`,
  `vectorizer_config.json`, and native XGBoost `model.json`. Provisioning reuses an existing
  registered HIVOTO lookup; runtime reconstructs the TF-IDF vectorizer without fitting or unpickling.
- **Behavior**: Uses compiled HIVOTO lookup hits and predicts female probability for lookup misses
  with TF-IDF + XGBoost. Model tokens become `female` at probability `>= 0.5`, otherwise `male`.
  Its own reduction counts native hard labels excluding `andy` and `unknown`; the most frequent
  label wins, with ties resolved by first token occurrence. Only then are `mostly_*` winners
  collapsed to plain gender. If no hard labels exist, all-`andy` returns `andy`; otherwise the
  mean token probability is thresholded at `>= 0.5`. Empty tokens yield `no_name` and abstention.
  This is not the shared `conflict` consensus, and unknown lookup hits need not yield an overall
  unknown answer.
- **Evidence**: Raw output preserves ordered `tokens`, `token_results`, and `token_probabilities`
  rounded to four decimals; decisions use unrounded probabilities. No overall mean or
  `method_confidence` is emitted. The adapter's reduction emits raw `male`, `female`, `andy`, or
  `no_name`; its normalization profile additionally supports `mostly_*`, `conflict`, and `unknown`.

## Governing ADRs and specifications

| Method Component | Module Path | Governing ADR |
|---|---|---|
| Parenthetical Qualifier | [`gendertagger.methods.adapters.parenthetical_qualifier`](../backend/src/gendertagger/methods/adapters/parenthetical_qualifier.py) | [ADR-0010](decisions/ADR-0010-parenthetical-qualifier-adapter.md), [ADR-0014](decisions/ADR-0014-restore-parenthetical-institution-normalization.md) |
| GND Local Snapshot | [`gendertagger.methods.adapters.gnd`](../backend/src/gendertagger/methods/adapters/gnd.py) | [ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md), [ADR-0046](decisions/ADR-0046-gnd-entity-type-precedence.md) |
| GND lookup compiler (offline, not a method) | [`gendertagger.methods.gnd_snapshot`](../backend/src/gendertagger/methods/gnd_snapshot.py) | [ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md) |
| gender-guesser | [`gendertagger.methods.adapters.gender_guesser`](../backend/src/gendertagger/methods/adapters/gender_guesser.py) | [ADR-0012](decisions/ADR-0012-name-based-classifier-adapter-pattern.md) |
| Wiki-Gendersort | [`gendertagger.methods.adapters.wiki_gendersort`](../backend/src/gendertagger/methods/adapters/wiki_gendersort.py) | [ADR-0045](decisions/ADR-0045-wiki-gendersort-compatible-implementation.md) |
| HIVOTO | [`gendertagger.methods.adapters.hivoto`](../backend/src/gendertagger/methods/adapters/hivoto.py) | [ADR-0018](decisions/ADR-0018-hivoto-adapter.md), [ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md) |
| nomquamgender | [`gendertagger.methods.adapters.nomquamgender`](../backend/src/gendertagger/methods/adapters/nomquamgender.py) | [ADR-0019](decisions/ADR-0019-nomquamgender-adapter.md) |
| Hugging Face DistilBERT | [`gendertagger.methods.adapters.hf_distilbert`](../backend/src/gendertagger/methods/adapters/hf_distilbert.py) | [ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md) |
| Hugging Face BERT genderize | [`gendertagger.methods.adapters.hf_genderize`](../backend/src/gendertagger/methods/adapters/hf_genderize.py) | [ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md) |
| Local LLM | [`gendertagger.methods.adapters.local_llm`](../backend/src/gendertagger/methods/adapters/local_llm.py) | [ADR-0026](decisions/ADR-0026-local-llm-adapter.md) |
| HIVOTO-XGBoost | [`gendertagger.methods.adapters.hivoto_xgboost`](../backend/src/gendertagger/methods/adapters/hivoto_xgboost.py) | [ADR-0025](decisions/ADR-0025-hivoto-xgboost-adapter.md) |
