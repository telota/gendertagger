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

An unrecognized name is not an abstention: the name-based classifiers resolve it to a substantive
`unknown`, and only a person with no checkable forename token abstains.

### Execution inputs and outputs

Each adapter accepts a sequence of `PersonInput` objects and a resolved `MethodConfig`. Adapters return a list of `PredictionResult` objects matching the exact length and order of the inputs.

```text
PersonInput -> Adapter (GenderMethod) -> PredictionResult
```

### Shared forename tokenization and consensus

Seven adapters share the frozen token filter and per-token reduction in
[`gendertagger.methods.name_tokens`](../backend/src/gendertagger/methods/name_tokens.py): `usable_forename_tokens`
splits every value of `person.forenames` on whitespace and drops bracketed qualifiers, single-letter
initials, digit-leading fragments, dash-only fragments, and a fixed particle/noise-word set;
`consensus_label` then reduces the per-token labels by an adapter-declared priority ranking. It returns
`no_name` when no token survives (a shared abstain label) and `conflict` when definite male and female
tokens both occur (a substantive `unknown` for every name-based profile). HIVOTO-XGBoost reuses the
token filter but carries its own ported consensus reduction.

### Registration

[`gendertagger.services.method_registry`](../backend/src/gendertagger/services/method_registry.py) registers all
ten adapters with their descriptor, closed configuration model, routing queue, and batch size. Every
adapter routes to the `cpu` queue except `local_llm`, which routes to `llm`; the batch size is 200 for
all ten. Registrations that name a `data_artifact_logical_type` require a `LookupMethodConfig`, so run
scheduling can resolve `lookup_sha256` to a registered artifact before any batch is dispatched.

## Implemented method adapters

The pipeline contains ten components across five methodological families. Nine components participate in the reference ensemble (`reference_v1`), while HIVOTO-XGBoost is an experimental component.

### 1. Parenthetical Qualifier (`parenthetical_qualifier`)

- **Module**: [`gendertagger.methods.adapters.parenthetical_qualifier`](../backend/src/gendertagger/methods/adapters/parenthetical_qualifier.py)
- **ADR**: [ADR-0010](decisions/ADR-0010-parenthetical-qualifier-adapter.md), [ADR-0014](decisions/ADR-0014-restore-parenthetical-institution-normalization.md)
- **Role**: Authority override rule (highest priority in ensemble).
- **Dependencies**: Built-in standard library (regular expressions).
- **Configuration**: `ParentheticalQualifierConfig` (no additional parameters required).
- **Normalization Profile**: `parenthetical_qualifier_v1`.
- **Inputs Consumed**: `person.surname`, `person.forenames`, then `person.note`.
- **Behavior**: Scans parenthesized content in the surname and each forename for a relational keyword, preferring the leading word of the parenthesis and falling back to any word in it. Female kinship terms (`Frau`, `Tochter`, `Witwe`, ...) map to `female`, male ones (`Herr`, `Sohn`, `Bruder`, ...) to `male`, family-group terms (`Familie`, `Kinder`, `Geschwister`, `Ehepaar`, ...) to substantive `unknown`, and commercial/organisational terms (`Firma`, `Weinhandlung`, `Bankier`, `Kaufleute`) to `institution`. If no name field matches, the note is consulted, but only on its first word and never for `institution`. With no match the adapter emits no raw label at all and normalizes to `abstain`.

### 2. GND Local Snapshot (`gnd`)

- **Module**: [`gendertagger.methods.adapters.gnd`](../backend/src/gendertagger/methods/adapters/gnd.py), which defines the
  runtime `GndMethod` adapter registered under the method name `gnd`. The separate offline compiler
  [`gendertagger.methods.gnd_snapshot`](../backend/src/gendertagger/methods/gnd_snapshot.py) turns DNB
  MARC21-XML full dumps into the immutable SQLite lookup this adapter reads; it is not itself a
  classification method.
- **ADR**: [ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md)
- **Role**: Authority override lookup (second priority in ensemble).
- **Dependencies**: Built-in `sqlite3`.
- **Configuration**: `LookupMethodConfig` requiring `lookup_sha256` digest of the compiled GND SQLite artifact.
- **Normalization Profile**: `gnd_v1`.
- **Inputs Consumed**: `person.gnd_id`.
- **Behavior**: Queries local compiled SQLite database by GND identifier. Maps GND entity types and explicit sex codes: `Männlich` -> `male`, `Weiblich` -> `female`, corporate entities -> `institution`, missing/unclear -> `unknown`. Abstains as `no_gnd` when `gnd_id` is missing or not found.

### 3. gender-guesser (`gender_guesser`)

- **Module**: [`gendertagger.methods.adapters.gender_guesser`](../backend/src/gendertagger/methods/adapters/gender_guesser.py)
- **ADR**: [ADR-0012](decisions/ADR-0012-name-based-classifier-adapter-pattern.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Standard dependency (`gender-guesser`).
- **Configuration**: `GenderGuesserConfig` with optional `detector_type` (`"detector"` or `"cautious"`).
- **Normalization Profile**: `gender_guesser_v1`.
- **Inputs Consumed**: Primary forename from `person.forenames` or `person.name_forms`.
- **Behavior**: Evaluates the first forename token using the `gender_guesser` dictionary. Maps `male` / `mostly_male` -> `male`, `female` / `mostly_female` -> `female`, `andy` / `conflict` -> `unknown`, and `unknown` -> `abstain`.

### 4. Wiki-Gendersort (`wiki_gendersort`)

- **Module**: [`gendertagger.methods.adapters.wiki_gendersort`](../backend/src/gendertagger/methods/adapters/wiki_gendersort.py)
- **ADR**: [ADR-0013](decisions/ADR-0013-wiki-gendersort-adapter.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Built-in `sqlite3` and standard dependency `unidecode`.
- **Configuration**: `LookupMethodConfig` requiring `lookup_sha256` digest of the compiled Wiki-Gendersort SQLite artifact.
- **Normalization Profile**: `wiki_gendersort_v1`.
- **Inputs Consumed**: Forename tokens from `person.forenames` or `person.name_forms`.
- **Behavior**: Queries local SQLite frequency table for normalized forename tokens. Computes token-level consensus. Maps `M` -> `male`, `F` -> `female`, `UNI` / `unisex` -> `unknown`, `UNK` -> `unknown`, and abstains on unindexed names (`INI`).

### 5. HIVOTO (`hivoto`)

- **Module**: [`gendertagger.methods.adapters.hivoto`](../backend/src/gendertagger/methods/adapters/hivoto.py)
- **ADR**: [ADR-0018](decisions/ADR-0018-hivoto-adapter.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Built-in `sqlite3`.
- **Configuration**: `LookupMethodConfig` requiring `lookup_sha256` digest of the compiled HIVOTO SQLite artifact.
- **Normalization Profile**: `hivoto_v1`.
- **Inputs Consumed**: Forename tokens from `person.forenames` or `person.name_forms`.
- **Behavior**: Queries local compiled HIVOTO forename lookup table across all forename tokens. Applies multi-token voting rules across recognized names. Maps `mostly_*` and plain gender labels accordingly, mapping `andy` / `conflict` -> `unknown`.

### 6. nomquamgender (`nomquamgender`)

- **Module**: [`gendertagger.methods.adapters.nomquamgender`](../backend/src/gendertagger/methods/adapters/nomquamgender.py)
- **ADR**: [ADR-0019](decisions/ADR-0019-nomquamgender-adapter.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Standard dependency (`nomquamgender`).
- **Configuration**: `NomquamgenderConfig` (no additional parameters required).
- **Normalization Profile**: `nomquamgender_v1`.
- **Inputs Consumed**: Forename tokens from `person.forenames` or `person.name_forms`.
- **Behavior**: Runs `nomquamgender` classifier over forenames. Combines predictions across multiple tokens. Maps raw classification decisions to canonical labels or abstains when no forenames are provided or recognized.

### 7. Hugging Face DistilBERT (`hf_distilbert`)

- **Module**: [`gendertagger.methods.adapters.hf_distilbert`](../backend/src/gendertagger/methods/adapters/hf_distilbert.py)
- **ADR**: [ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Standard dependencies (`transformers`, `torch`).
- **Configuration**: `HfDistilbertConfig`, a `LookupMethodConfig` requiring `lookup_sha256` digest of the content-addressed model manifest.
- **Normalization Profile**: `hf_distilbert_v1`.
- **Inputs Consumed**: Primary forename string.
- **Behavior**: Runs local PyTorch DistilBERT model (`padmajabfrl/Gender-Classification`). Index `0` maps to `male`, index `1` maps to `female`. Reports softmax classification probability as `method_confidence`.

### 8. Hugging Face BERT genderize (`hf_genderize`)

- **Module**: [`gendertagger.methods.adapters.hf_genderize`](../backend/src/gendertagger/methods/adapters/hf_genderize.py)
- **ADR**: [ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Standard dependencies (`transformers`, `torch`).
- **Configuration**: `HfGenderizeConfig`, a `LookupMethodConfig` requiring `lookup_sha256` digest of the content-addressed model manifest.
- **Normalization Profile**: `hf_genderize_v1`.
- **Inputs Consumed**: Primary forename string.
- **Behavior**: Runs local PyTorch BERT model (`imranali291/genderize`). Index `0` maps to `female`, index `1` maps to `male`. Reports softmax classification probability as `method_confidence`.

### 9. Local LLM (`local_llm`)

- **Module**: [`gendertagger.methods.adapters.local_llm`](../backend/src/gendertagger/methods/adapters/local_llm.py)
- **ADR**: [ADR-0026](decisions/ADR-0026-local-llm-adapter.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Pooled voter in reference ensemble.
- **Dependencies**: Standard dependency (`httpx2`).
- **Configuration**: `LocalLlmConfig` requiring `model` and `base_url`, with optional `api_key`, `system_prompt`, `temperature`, and `max_validation_retries`.
- **Normalization Profile**: `local_llm_v1`.
- **Inputs Consumed**: Complete record (`person.tei_id`, names, life dates, `person.note`, `person.events`, `person.gnd_id`, `person.external_ids`).
- **Behavior**: Synthesizes prompt and executes HTTP request against OpenAI-compatible local API (e.g. Ollama, vLLM). Enforces structured JSON schema response (`PersonClassification`). Maps `organisation` -> `institution`, and raw `male`/`female`/`institution`/`unknown` directly. Records self-reported certainty (`high`/`low`/`uncertain`) in prediction metadata.

### 10. HIVOTO-XGBoost (`hivoto_xgboost`) [Experimental]

- **Module**: [`gendertagger.methods.adapters.hivoto_xgboost`](../backend/src/gendertagger/methods/adapters/hivoto_xgboost.py)
- **ADR**: [ADR-0025](decisions/ADR-0025-hivoto-xgboost-adapter.md), [ADR-0029](decisions/ADR-0029-unconditional-method-dependencies.md)
- **Role**: Experimental component (held out from `reference_v1` voting ensemble).
- **Dependencies**: Standard dependencies (`scikit-learn`, `xgboost`).
- **Configuration**: `LookupMethodConfig` requiring `lookup_sha256` digest of model manifest.
- **Normalization Profile**: `hivoto_xgboost_v1`.
- **Inputs Consumed**: Forename tokens from `person.forenames` or `person.name_forms`.
- **Behavior**: Two-stage classifier: checks compiled HIVOTO SQLite lookup table for forename tokens, falling back to a trained TF-IDF + XGBoost model for unindexed tokens. Majority votes hard labels across tokens or thresholds mean predicted probability.

## Governing ADRs and specifications

| Method Component | Module Path | Governing ADR |
|---|---|---|
| Parenthetical Qualifier | [`gendertagger.methods.adapters.parenthetical_qualifier`](../backend/src/gendertagger/methods/adapters/parenthetical_qualifier.py) | [ADR-0010](decisions/ADR-0010-parenthetical-qualifier-adapter.md), [ADR-0014](decisions/ADR-0014-restore-parenthetical-institution-normalization.md) |
| GND Local Snapshot | [`gendertagger.methods.adapters.gnd`](../backend/src/gendertagger/methods/adapters/gnd.py) | [ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md) |
| GND lookup compiler (offline, not a method) | [`gendertagger.methods.gnd_snapshot`](../backend/src/gendertagger/methods/gnd_snapshot.py) | [ADR-0023](decisions/ADR-0023-content-addressed-sqlite-method-lookups.md) |
| gender-guesser | [`gendertagger.methods.adapters.gender_guesser`](../backend/src/gendertagger/methods/adapters/gender_guesser.py) | [ADR-0012](decisions/ADR-0012-name-based-classifier-adapter-pattern.md) |
| Wiki-Gendersort | [`gendertagger.methods.adapters.wiki_gendersort`](../backend/src/gendertagger/methods/adapters/wiki_gendersort.py) | [ADR-0013](decisions/ADR-0013-wiki-gendersort-adapter.md) |
| HIVOTO | [`gendertagger.methods.adapters.hivoto`](../backend/src/gendertagger/methods/adapters/hivoto.py) | [ADR-0018](decisions/ADR-0018-hivoto-adapter.md) |
| nomquamgender | [`gendertagger.methods.adapters.nomquamgender`](../backend/src/gendertagger/methods/adapters/nomquamgender.py) | [ADR-0019](decisions/ADR-0019-nomquamgender-adapter.md) |
| Hugging Face DistilBERT | [`gendertagger.methods.adapters.hf_distilbert`](../backend/src/gendertagger/methods/adapters/hf_distilbert.py) | [ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md) |
| Hugging Face BERT genderize | [`gendertagger.methods.adapters.hf_genderize`](../backend/src/gendertagger/methods/adapters/hf_genderize.py) | [ADR-0024](decisions/ADR-0024-hf-transformer-model-manifest-adapters.md) |
| Local LLM | [`gendertagger.methods.adapters.local_llm`](../backend/src/gendertagger/methods/adapters/local_llm.py) | [ADR-0026](decisions/ADR-0026-local-llm-adapter.md) |
| HIVOTO-XGBoost | [`gendertagger.methods.adapters.hivoto_xgboost`](../backend/src/gendertagger/methods/adapters/hivoto_xgboost.py) | [ADR-0025](decisions/ADR-0025-hivoto-xgboost-adapter.md) |
