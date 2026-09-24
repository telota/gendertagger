# Production Promotion

This document describes manual promotion of a tested, CI-built `gendertagger` commit to production.
Image publication does not deploy anything. The local-image workflow in
[QUICKSTART.md](../QUICKSTART.md) remains available for development and locally built installations;
this runbook promotes already-published images without rebuilding them on the deployment host.

## Prerequisites

1. **Published commit**: Select a successful default-branch pipeline that published both
   `$CI_REGISTRY_IMAGE/backend:$CI_COMMIT_SHA` and `$CI_REGISTRY_IMAGE/frontend:$CI_COMMIT_SHA`.
   Both images must use the same full commit SHA. CI also updates the default branch's
   `$CI_COMMIT_REF_SLUG` alias (`main`), but that moving alias is not a deployment or rollback target.
   Version/release-tag pipelines do not currently publish images; do not assume that a `v1.2.3` tag exists.
2. **Artifact identity and retention**: Save `backend-image.txt`, `frontend-image.txt`,
   `backend-sbom.json`, and `frontend-sbom.json` from that pipeline in the deployment record. The
   image-reference files identify the exact image digests used by the SBOM jobs. A commit tag identifies
   source; its digest identifies the built artifact, and rebuilding the same source can change that
   digest. Pipeline artifacts expire after one week by default: retain the target and previous
   deployment records separately, and keep both deployments' images in the registry for rollback.
3. **Backup**: Take a fresh backup of PostgreSQL and artifact storage immediately before deployment.
   Use `deploy/scripts/backup.sh` only with its expected Compose project and named-volume layout;
   installations with bind mounts need their corresponding verified backup procedure.
4. **Independent migration rehearsal**: Rehearse the target image's migrations against an isolated
   staging copy of the actual previous schema and representative data, and verify application startup
   and the restore procedure there. `deploy/scripts/test_migration.sh` is not evidence of a
   previous-to-current upgrade: it starts PostgreSQL without establishing the previous application
   schema, and its host-side readiness probe has no corresponding API port published by
   `compose.test.yaml`. Do not use that helper as this promotion gate.

## Promotion Steps

### 1. Select the Matching Checkout and Environment

Use a clean checkout of the selected full commit SHA for the Compose files and operational scripts.
Do not combine a newer checkout with older images, and do not update the production checkout to a moving
branch tip as part of promotion. Preserve the existing `.env`, Compose project name, storage locations,
secrets, and deployment-specific overrides.

Update these values in the production `.env`, replacing the placeholders with the selected pipeline's
values. `CI_REGISTRY_IMAGE` is the project registry path reported by GitLab CI, without an image name;
copy it exactly and add the trailing `/`. CI variables are not automatically available on the server.

```bash
REGISTRY_PREFIX=REPLACE_WITH_CI_REGISTRY_IMAGE/
TAG=REPLACE_WITH_FULL_CI_COMMIT_SHA
GENDERTAGGER_CODE_GIT_COMMIT=REPLACE_WITH_SAME_FULL_COMMIT_SHA
GENDERTAGGER_DEPENDENCY_LOCK_SHA256=REPLACE_WITH_MATCHING_LOCKFILE_SHA256
```

From the matching checkout, confirm the commit and calculate the lockfile hash:

```bash
git rev-parse HEAD
sha256sum backend/uv.lock
```

The resulting image names are `<CI_REGISTRY_IMAGE>/backend:<full-SHA>` and
`<CI_REGISTRY_IMAGE>/frontend:<full-SHA>`. Ensure stale exported shell variables do not override the
chosen `.env` values. Record these values, both image digests, the previous deployment's corresponding
values, and the backup location before continuing.

### 2. Pull New Images

Authenticate to the project registry using the deployment host's authorized credentials. Confirm the
resolved image names, then pull the core services and every optional profile active in this deployment:

```bash
docker compose -f compose.yaml -f compose.prod.yaml config --images
docker compose -f compose.yaml -f compose.prod.yaml pull

# Also pull any active optional profiles, for example LLM.
docker compose -f compose.yaml -f compose.prod.yaml --profile llm pull
```

Compare the pulled backend and frontend `RepoDigests` from `docker image inspect` with the recorded
pipeline digest references. Stop if either differs or is unavailable; do not silently use a locally
built image or rebuild the target. Do not include `compose.dev.yaml` in production promotion.

### 3. Apply Database Migrations

Run the one-shot migration service using the selected backend image. It applies Alembic migrations and
exits; continue only after it succeeds.

```bash
docker compose -f compose.yaml -f compose.prod.yaml --profile ops run --rm migrate
```

### 4. Restart Services

Recreate services with the pulled images, explicitly disabling builds. The default services are `db`,
`redis`, `api`, `worker-cpu`, `dispatch-coordinator`, `frontend`, and `gateway`; the coordinator must run
alongside the API and workers. Include every optional profile enabled in this deployment.

```bash
# Recreate core services without rebuilding images.
docker compose -f compose.yaml -f compose.prod.yaml up -d --no-build

# Recreate optional profiles if enabled, for example LLM.
docker compose -f compose.yaml -f compose.prod.yaml --profile llm up -d --no-build
```

### 5. Verify Health and Readiness

Check the health status of the deployed containers.

```bash
docker compose -f compose.yaml -f compose.prod.yaml ps
```

Ensure every service with a healthcheck reports `Up (healthy)`. `dispatch-coordinator` defines no healthcheck and reports plain `Up`; confirm it separately by checking that its log shows relay and reconciliation cycles and that `dispatch_outbox` rows are not accumulating in `pending`. Without it, queued work is persisted but never published to the broker.

Wait a few moments for the startup sequence to complete, then test the external endpoints. `/health` and `/ready` are served at the root, not under `/api/v1` (for example `https://your-domain.com/health`).

## Administrative Branding Overrides

Apply the singleton settings migration before starting an API release that serves ADR-0040 settings-backed
branding. Every API replica must be deployed with equivalent `GENDERTAGGER_BRANDING__*` fallback values:
stored overrides are shared, but inherited fields resolve in each process. Coordinate environment changes as a
single rollout to avoid replica-dependent branding at the same settings revision.

An older application release ignores stored overrides and displays environment branding. Rolling back only the
application image is therefore database-compatible, but administrators' committed overrides remain in the
database and become effective again after restoring a settings-aware release. Do not roll back the migration
or restore a database backup merely to hide an override; reset it through the administrative API when the
settings-aware release is available.

## Rollback Procedure

If health checks fail or critical errors are identified, use the independently rehearsed rollback plan:

1. Restore the previous deployment's matching checkout, registry prefix, full-SHA `TAG`, Git provenance,
   and lockfile hash. Pull its retained backend and frontend images and verify their recorded digests.
2. Determine whether the previous application can safely use the current schema and data. If so,
   recreate it using the commands above with `--no-build`; do not restore the database unnecessarily.
3. If schema/data compatibility requires a restore, stop application writes and use the rehearsed
   database-and-artifact restore procedure before starting the previous application. A restore is
   destructive and discards later changes. `deploy/scripts/restore.sh` requires a running target
   database container and its expected named-volume layout; it cannot run immediately after a blanket
   `docker compose down` has removed that container.
4. Verify health, readiness, and coordinator operation again, and record the rollback outcome.
