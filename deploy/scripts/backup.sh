#!/usr/bin/env bash
set -euo pipefail

# This script performs a backup of the PostgreSQL database and the artifacts directory.
# It assumes it is run from the repository root on the Docker host where the Compose project is running.

COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-gendertagger}
BACKUP_DIR=${BACKUP_DIR:-./backups/$(date +%Y%m%d_%H%M%S)}
DB_CONTAINER="${COMPOSE_PROJECT_NAME}-db-1"
POSTGRES_USER=${POSTGRES_USER:-postgres}
POSTGRES_DB=${POSTGRES_DB:-gendertagger}

echo "Starting backup to ${BACKUP_DIR}..."

mkdir -p "${BACKUP_DIR}"

echo "Backing up PostgreSQL database..."
if ! docker exec -t "${DB_CONTAINER}" pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -F c -f "/tmp/db_backup.dump"; then
    echo "ERROR: Failed to run pg_dump inside container ${DB_CONTAINER}."
    exit 1
fi

docker cp "${DB_CONTAINER}:/tmp/db_backup.dump" "${BACKUP_DIR}/db_backup.dump"
docker exec -t "${DB_CONTAINER}" rm "/tmp/db_backup.dump"

echo "Backing up artifacts directory..."
# Use tar inside a temporary alpine container that mounts the artifacts volume
docker run --rm -v "${COMPOSE_PROJECT_NAME}_artifacts:/source_artifacts" -v "$(pwd)/${BACKUP_DIR}:/backup" alpine tar -czf "/backup/artifacts_backup.tar.gz" -C "/source_artifacts" .

echo "Backup completed successfully at ${BACKUP_DIR}."
