# ADR-0002: Projects contain immutable DatasetSnapshots

**Status:** Accepted

## Context

Runs must remain reproducible when source TEI changes over time.

## Decision

A Project is long-lived. Every import creates a new immutable DatasetSnapshot. A Run references exactly one snapshot.

TEI `xml:id` is canonical within the Project and links the conceptual person entry across snapshots.

## Consequences

- historical runs always retain a stable input state
- snapshot diffs can be implemented later
- source storage cost increases modestly
- updates create snapshots rather than mutating ready data
