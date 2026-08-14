# ADR-0026: Local LLM classification adapter

**Status:** Accepted

## Context

The local LLM classifier (`gpt-oss:20b` served locally in the reference study) is one of the nine published components included in the reference voting ensemble (see [`07-methods-and-aggregation.md`](../07-methods-and-aggregation.md)). Unlike name-only lookup or rule-based classifiers, the local LLM evaluates complete historical person records — including names, life dates, biographical notes, events, GND identifiers, and external authority IDs — to produce structured gender classifications.

In the reference workflow, local LLM execution requires a private, locally hosted model (such as Ollama or vLLM presenting an OpenAI-compatible HTTP API) to comply with local-first operational rules ([ADR-0005](ADR-0005-local-first-data-processing.md)). The LLM server is provisioned out-of-band and configured via `LLM_BASE_URL`, keeping the core application independent of model management. The adapter must produce structured JSON output containing gender, confidence, self-reported certainty, and reasoning while maintaining strict contract boundaries, versioned normalization profiles ([ADR-0007](ADR-0007-versioned-normalization-outcomes.md)), and pipeline certainty mapping ([ADR-0009](ADR-0009-reference-agreement-certainty.md)).

## Decision

Implement `LocalLlmMethod` in `gendertagger.methods.local_llm` conforming to `GenderMethod[LocalLlmConfig]`:

1. **HTTP Client & Dependency Isolation**:
   - The adapter uses a lightweight, minimal HTTP client wrapper (`LlmClient`) over `httpx` to target OpenAI-compatible `/v1/chat/completions` endpoints.
   - `httpx` is declared as an opt-in `llm` extra (`"httpx>=0.27,<1"`). If absent, invoking `predict_batch` raises `MethodDependencyError`, preserving the slim default installation footprint for non-LLM workers.

2. **Configuration Contract**:
   - `LocalLlmConfig` requires `model` (e.g. `"gpt-oss:20b"` or `"llama3"`) and `base_url` (e.g. `"http://localhost:11434/v1"`).
   - Configuration allows optional `api_key` (defaulting to `"ollama"`), `system_prompt` (defaulting to `"You are an expert archivist identifying the gender of historical persons."`), `temperature` (defaulting to `0.0`), and `max_validation_retries` (defaulting to `2`).

3. **Structured Output & Prompt Synthesis**:
   - Requests structured JSON matching the `PersonClassification` Pydantic model (`gender`: `Literal["female", "male", "institution", "unknown"]`, `confidence`: `float`, `certainty`: `Literal["high", "low", "uncertain"]`, `reasoning`: `str | None`).
   - If output validation fails, `LlmClient` performs semantic retry attempts up to `max_validation_retries`, appending validation feedback to the conversation context before re-requesting JSON output.
   - `_build_prompt` synthesizes prompt strings from `PersonInput`, incorporating `tei_id`, primary and alternative name forms (from `name_forms` or forenames/surname), life dates, biographical notes, events, GND IDs, and external authority IDs.

4. **Normalization & Provenance**:
   - `LOCAL_LLM_NORMALIZATION` (`local_llm_v1` profile) maps raw `male`, `female`, `institution`, and `unknown` directly to canonical labels, with `organisation` mapping to `institution`.
   - Raw completion responses, prompt parameters (`model`, `temperature`, `attempt_count`), reasoning, and `self_reported_certainty` are captured in `PredictionResult.metadata` and `raw_output`.
   - Record-level transport or validation exceptions produce an `error` status result without crashing the batch execution.

## Consequences

- The local LLM adapter integrates seamlessly into Celery CPU worker queues via standard HTTP requests to local model endpoints.
- No heavy LLM framework dependencies (e.g., LangChain, LlamaIndex) are introduced into the project.
- Self-reported certainty (`high`/`low`/`uncertain`) is recorded in prediction metadata and correctly drives lone-voter certainty tier evaluation ([ADR-0009](ADR-0009-reference-agreement-certainty.md)).
- Network timeouts, endpoint errors, or invalid JSON schema outputs per person record produce explicit `error` prediction status results, preserving batch completeness and downstream aggregation transparency.
