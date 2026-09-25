# Project status

This file is the current implementation-status summary. The authoritative phased plan is in
[`docs/15-implementation-plan.md`](docs/15-implementation-plan.md), which owns scope, sequencing, and exit
criteria. Implementation rules live in [`AGENTS.md`](AGENTS.md), and deferred scope lives in
[`docs/22-future-development.md`](docs/22-future-development.md).

## Current status

Phases 0 through 7 are complete. All nine reference method adapters are implemented and registered
alongside the experimental HIVOTO-XGBoost adapter, and the asynchronous snapshot-import, lookup-asset,
method-execution, reference-aggregation, evaluation, and export paths all run end to end through the
persisted API-to-worker workflow.

Active work is Phase 8, the annotation and review client. Its backend prerequisites are already met:
the review-items query API is stable and review-stream revision conflicts return `409`. The remaining
review-client items are frontend work: `frontend/` holds the scaffold and transport layer (milestone M1),
the local account backend from [ADR-0031](docs/decisions/ADR-0031-local-database-authentication.md) gives it a
real session to sign in to, and the application shell and every screen remain to be built. The read
endpoints and collections the screens need are delivered; see
[`docs/24-frontend-delivery-plan.md`](docs/24-frontend-delivery-plan.md). The second active track is
operating the stack in production following [`docs/21-production-promotion.md`](docs/21-production-promotion.md).

Account-level presentation preferences are delivered as a bounded backend increment under
[ADR-0043](docs/decisions/ADR-0043-account-level-user-preferences.md): locale, theme, and explicit desktop
sidebar collapse, owned by the existing local account with revision-checked updates. The implementation includes the
forward migration, `/api/v1/me/preferences` reads/writes, meaningful PostgreSQL/API tests, and generated
transport updates. The personal settings page and integration of existing browser controls are deferred to
a later increment; see the
[delivery sequence](docs/15-implementation-plan.md#account-preferences-increment-adr-0043).

Administrative branding settings are a separate accepted extension under
[ADR-0040](docs/decisions/ADR-0040-administrative-branding-overrides.md). Its backend persistence, reads,
writes, and public-branding integration are delivered; the permitted frontend settings work remains pending.
The separate frontend administrative increment delivers only the read-only local-account directory from
[ADR-0039](docs/decisions/ADR-0039-administer-local-accounts-over-http.md), and stops before settings forms
or branding-consumer changes. Scope, sequencing, and acceptance criteria are recorded in
[`docs/15-implementation-plan.md`](docs/15-implementation-plan.md#administrative-settings-increment-adr-0040).
