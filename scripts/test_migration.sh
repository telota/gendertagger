#!/usr/bin/env bash
set -euo pipefail

# Rehearses a migration from the previous release to the current release.

echo "Starting migration rehearsal..."

PREVIOUS_RELEASE_TAG=${PREVIOUS_RELEASE_TAG:-latest}
CURRENT_RELEASE_TAG=${CURRENT_RELEASE_TAG:-latest}

export COMPOSE_PROJECT_NAME="gendertagger-migration-test"

# Boot the previous release database and api to seed schema
echo "Booting previous release database ($PREVIOUS_RELEASE_TAG)..."
TAG=$PREVIOUS_RELEASE_TAG docker compose -f compose.yaml -f compose.test.yaml up -d db

# Wait for DB to be healthy
echo "Waiting for database to be healthy..."
sleep 10 # Ideally, poll the healthcheck status

# Run migrations to the latest state of the CURRENT codebase
echo "Running migrations with current release..."
TAG=$CURRENT_RELEASE_TAG docker compose -f compose.yaml -f compose.test.yaml --profile ops run --rm migrate

# Boot current API to ensure it starts cleanly against the migrated database
echo "Booting current API release..."
TAG=$CURRENT_RELEASE_TAG docker compose -f compose.yaml -f compose.test.yaml up -d api

# Wait for API to be healthy
echo "Waiting for API to be healthy..."
sleep 10

echo "Checking API readiness..."
if ! curl -sSf http://localhost:8000/ready > /dev/null; then
    echo "ERROR: API failed readiness check after migration."
    docker compose -f compose.yaml -f compose.test.yaml logs api
    docker compose -f compose.yaml -f compose.test.yaml down -v
    exit 1
fi

echo "Migration rehearsal and smoke test successful."

# Clean up
docker compose -f compose.yaml -f compose.test.yaml down -v
