# Future development

This document tracks planned architectural expansions, advanced capabilities, and optional features that extend beyond the baseline production system.

## Multi-host topology and Compose scaling

The core architecture supports single-host Docker Compose deployment as well as distributed production deployments. Future infrastructure expansions include:

- Splitting API, asynchronous Celery workers, and caching layers onto dedicated host pools.
- Horizontal autoscaling for CPU-intensive and GPU/LLM worker queues.
- Centralized log streaming, OpenTelemetry metrics collection, and distributed tracing.

## Label-bearing dataset imports and ground-truth ingestion

Currently, dataset snapshots import structural person registers without predefined gender labels. Future ingestion profiles can support:

- Ingesting curated ground-truth datasets with pre-annotated historical or reference labels.
- Automated benchmark dataset synthesis from external gold-standard registers.
- Differential reconciliation between snapshot source records and external authority files.

## Schema evolution and partitioning strategies

As datasets and run histories scale:

- PostgreSQL table partitioning by snapshot or run for large-scale predictions and aggregation tables.
- Cold-storage archival and compression policies for historical, unreferenced runs.
- Continuous vacuuming and index maintenance strategies for high-churn outbox dispatch tables.

## Task queue tuning and specialized worker pools

The Celery and Redis pipeline is organized into distinct queues (`cpu`, `io`, `llm`, `dispatch`). Future tuning includes:

- Fine-tuning Celery worker concurrency, prefetch limits, and ACK-after-completion behavior under high load.
- Dynamic queue routing based on method resource profiles and batch sizes.
- Dead-letter queue analysis and automated alert dispatching for transient network failures.

## Alternative aggregation strategies

The normative baseline reproduces the published reference aggregation strategy. Future research and feature extensions include:

- Weighted voting and calibration curves based on method-specific historical performance.
- Bayesian aggregation models combining method confidence distributions.
- User-configurable custom ensemble strategies with reproducibility manifests.

## Advanced ingestion, manifest management, and export

Extended capabilities for dataset snapshot ingestion and result export include:

- Reference-aware artifact garbage collection with mark-and-sweep reference validation.
- Idempotent HTTP snapshot acceptance using client-supplied request tokens.
- Resumable streaming exports and delta exports comparing consecutive snapshot versions.

## Evaluation suites and benchmark reporting

Benchmark evaluation is defined by `EvaluationDefinition`:

- Expanding beyond the GND baseline to multi-source consensus benchmarks.
- Automated generation of comparative performance reports across multiple runs and model revisions.
- Extended Cohen's kappa and inter-annotator agreement metrics across diverse register formats.
