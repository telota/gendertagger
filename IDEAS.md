# Ideas

- Import registers from a Git URL.
- Train a classifier on GND data, bracketed by century and using each person's date of birth.
- Re-run the combined test suite when Docker is healthy, verify coverage of
  `db/repositories/aggregation_repository.py`, and add focused tests if material branches remain uncovered.

## Streamlined deployment and data/model provisioning

Make deployment and provisioning of required data and models simpler and more user-friendly. Aim for
a clear path from a fresh installation to a ready-to-use instance, with fewer manual commands and less
knowledge of internal services or filesystem layouts required.

Potential improvements:

- Provide a guided setup workflow and one coherent guide for installation, updates, and provisioning.
- Explain which datasets and models each method needs, which are optional, and their storage and
  hardware requirements.
- Simplify downloading or importing assets, validating them, and making them available to the relevant
  services, while preserving version/checksum provenance and respecting licensing requirements.
- Show what is ready, missing, or misconfigured, with actionable next steps and safe retries.

Keep local/private and offline provisioning supported. This is a future improvement idea, not an
approved implementation design.

## Publication checklist

### Release identity and archival

- [ ] Keep the development version at `0.0.0`; set `0.1.0` for the first public, citable release.
- [ ] Create and verify an annotated `v0.1.0` tag from the exact reviewed commit.
- [ ] Add release notes covering supported workflows, limitations, deferred features, breaking changes, and migration policy.
- [ ] Provide citation metadata and an archival release/DOI for scholarly software publication.
- [ ] Record the release commit, image digests, lockfile checksums, and SBOMs with release artefacts.

### Database and deployment

- [ ] Decide the migration cutoff before squashing; no deployed database currently needs a compatibility path.
- [ ] Create a fresh-install migration baseline and test it against an empty PostgreSQL database.
- [ ] Rehearse upgrade, backup, restore, and rollback/recovery before the first shared deployment.
- [ ] Verify a clean checkout can install, provision assets, build images, migrate, and start the documented stack.

### Verification and security

- [ ] Run the complete CI-equivalent matrix: fast, PostgreSQL, Redis, frontend, package-build, contract, and deployment checks.
- [ ] Exercise one supported end-to-end workflow using sample data: import → run → aggregation → review → export.
- [ ] Run locked dependency and image vulnerability scans; resolve or document accepted findings.
- [ ] Run secret and sensitive-content checks; confirm no credentials, private corpora, personal data, databases, model weights, or unintended build artefacts are tracked.
- [ ] Verify the OpenAPI snapshot and generated frontend transport are current.

### Documentation and language

- [ ] Review milestone statuses, README, deployment guide, and deferred-scope statements for accurate current status.
- [ ] Apply the English-language policy to technical documentation, identifiers, diagnostics, and release notes; retain original-language quotations only where necessary.
- [ ] Publish a concise quickstart with prerequisites, local/private deployment, asset provisioning, first workflow, and troubleshooting.
- [ ] Document method and data-model limitations, uncertainty semantics, evaluation boundaries, and non-goals.
- [ ] Review legal notice, privacy wording, accessibility statement and feedback ownership, licence text, and third-party attribution.

### Sample data and reproducibility

- [ ] Provide a small, licensed, synthetic or explicitly cleared sample dataset; never ship unapproved editorial or personal data.
- [ ] Include a documented expected workflow and deterministic expected outputs/checksums.
- [ ] State sample provenance, licences, generation process, and applied transformations.
- [ ] Ensure sample data exercises supported input formats and the intended offline demonstration path without external services or models.
- [ ] Record exact method assets, model revisions, authority snapshots, and checksums needed to reproduce published results.

### Repository polish

- [ ] Remove abandoned scaffolding, stale documentation branches, dead code, obsolete fixtures, and generated artefacts not intended for release.
- [ ] Review `.gitignore`, distribution manifests, Docker contexts, and package contents so only intended artefacts ship.
- [ ] Consolidate duplicated instructions and make one command or document authoritative for each operational task.
- [ ] Verify licences for code, dependencies, datasets, models, authority snapshots, and bundled assets.

**Migration risk.** Squashing is safe now because no external environment depends on the development-only
chain. Once the baseline is committed, preserve it and provide a documented upgrade or rebuild procedure
before any shared deployment.
