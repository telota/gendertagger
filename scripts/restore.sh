#!/usr/bin/env bash
set -euo pipefail

# This script restores a backup of the PostgreSQL database and the artifacts directory.
# WARNING: This will overwrite existing data. Ensure you have targeted the correct environment.
# Usage: ./scripts/restore.sh path/to/backup_directory

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 path/to/backup_directory"
    exit 1
fi

BACKUP_DIR="$1"
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-gendertagger}
DB_CONTAINER="${COMPOSE_PROJECT_NAME}-db-1"
POSTGRES_USER=${POSTGRES_USER:-postgres}
POSTGRES_DB=${POSTGRES_DB:-gendertagger}

if [ ! -d "${BACKUP_DIR}" ]; then
    echo "ERROR: Backup directory ${BACKUP_DIR} does not exist."
    exit 1
fi

echo "Starting restore from ${BACKUP_DIR}..."

echo "Restoring artifacts directory..."
# First, clear existing artifacts (optional but recommended for a clean restore)
docker run --rm -v "${COMPOSE_PROJECT_NAME}_artifacts:/target_artifacts" alpine sh -c "rm -rf /target_artifacts/*"
# Extract backup archive to volume
docker run --rm -v "${COMPOSE_PROJECT_NAME}_artifacts:/target_artifacts" -v "$(cd "${BACKUP_DIR}" && pwd):/backup" alpine tar -xzf "/backup/artifacts_backup.tar.gz" -C "/target_artifacts"

echo "Restoring PostgreSQL database..."
docker cp "${BACKUP_DIR}/db_backup.dump" "${DB_CONTAINER}:/tmp/db_backup.dump"
# Terminate existing connections and drop/recreate DB if necessary.
# For pg_restore with clean, use -c.
if ! docker exec -t "${DB_CONTAINER}" pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -1 -c "/tmp/db_backup.dump"; then
    echo "ERROR: Database restore failed."
    exit 1
fi

docker exec -t "${DB_CONTAINER}" rm "/tmp/db_backup.dump"

echo "Restore completed successfully."
