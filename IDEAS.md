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
