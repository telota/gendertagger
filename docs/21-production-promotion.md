# Production Promotion

This document outlines the Standard Operating Procedure (SOP) for promoting a tested release of `gendertagger` to the production environment.

## Prerequisites
1. **Immutable Artifacts**: Ensure the target commit has been built by GitLab CI and the Docker images (`backend`, `frontend`) are pushed to the container registry with explicit tags (e.g., `v1.2.3`).
2. **Database Backup**: A fresh backup of the PostgreSQL database and the artifacts volume must be taken immediately before deployment. Use the `scripts/backup.sh` script.
3. **Migration Rehearsal**: The migration must have been successfully rehearsed against a staging environment or using the `scripts/test_migration.sh` script. That script drives an isolated `gendertagger-migration-test` Compose project from `compose.yaml` plus `compose.test.yaml`, booting the previous release's database (`PREVIOUS_RELEASE_TAG`) before applying the current release's migrations (`CURRENT_RELEASE_TAG`).

## Promotion Steps

### 1. Update Environment Variables
Update the `.env` file on the production host to point to the new image tag.
```bash
TAG=v1.2.3
```

### 2. Pull New Images
Pull the images for the core services and any active profiles.
```bash
docker compose -f compose.yaml -f compose.prod.yaml pull
```

### 3. Apply Database Migrations
Run the one-shot migration service. This will start the `migrate` container using the new backend image, apply Alembic migrations, and exit.
```bash
docker compose -f compose.yaml -f compose.prod.yaml --profile ops run --rm migrate
```

### 4. Restart Services
Restart the services to recreate the containers with the newly pulled images. The default (profile-less) services are `db`, `redis`, `api`, `worker-cpu`, `dispatch-coordinator`, `frontend`, and `gateway`, so this command brings up the dispatch coordinator alongside the API and workers.
```bash
# Restart core services
docker compose -f compose.yaml -f compose.prod.yaml up -d

# Restart optional profiles if enabled, e.g., LLM
docker compose -f compose.yaml -f compose.prod.yaml --profile llm up -d
```

### 5. Verify Health and Readiness
Check the health status of the deployed containers.
```bash
docker compose -f compose.yaml -f compose.prod.yaml ps
```
Ensure every service with a healthcheck reports `Up (healthy)`. `dispatch-coordinator` defines no healthcheck and reports plain `Up`; confirm it separately by checking that its log shows relay and reconciliation cycles and that `dispatch_outbox` rows are not accumulating in `pending`. Without it, queued work is persisted but never published to the broker.

Wait a few moments for the startup sequence to complete, then test the external endpoints. `/health` and `/ready` are served at the root, not under `/api/v1` (for example `https://your-domain.com/health`).



## Rollback Procedure
If the health checks fail or critical errors are identified:
1. Revert the `.env` file to the previous `TAG`.
2. Stop the current deployment: `docker compose -f compose.yaml -f compose.prod.yaml down`.
3. Restore the pre-deployment database backup using `scripts/restore.sh`.
4. Bring up the previous release: `docker compose -f compose.yaml -f compose.prod.yaml up -d`.
