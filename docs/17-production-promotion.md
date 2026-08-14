# Production Promotion

This document outlines the Standard Operating Procedure (SOP) for promoting a tested release of `genderTagger` to the production environment.

## Prerequisites
1. **Immutable Artifacts**: Ensure the target commit has been built by GitLab CI and the Docker images (`backend`, `frontend`) are pushed to the container registry with explicit tags (e.g., `v1.2.3`).
2. **Database Backup**: A fresh backup of the PostgreSQL database and the artifacts volume must be taken immediately before deployment. Use the `scripts/backup.sh` script.
3. **Migration Rehearsal**: The migration must have been successfully rehearsed against a staging environment or using the `scripts/test_migration.sh` script.

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
Restart the services to recreate the containers with the newly pulled images.
```bash
# Restart core services
docker compose -f compose.yaml -f compose.prod.yaml up -d

# Restart optional profiles if enabled, e.g., LLM
docker compose -f compose.yaml -f compose.prod.yaml --profile llm up -d
```

### 5. Verify Health and Readiness
Check the health status of the deployed containers.
```bash
docker compose ps
```
Ensure all services report as `Up (healthy)`. Wait a few moments for the startup sequence to complete, then test the external endpoints (e.g., `https://your-domain.com/api/v1/health`).



## Rollback Procedure
If the health checks fail or critical errors are identified:
1. Revert the `.env` file to the previous `TAG`.
2. Stop the current deployment: `docker compose down`.
3. Restore the pre-deployment database backup using `scripts/restore.sh`.
4. Bring up the previous release: `docker compose up -d`.
