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
the review-items query API is stable and review-stream revision conflicts return `409`. The client now
includes the application shell, project/import/run flows, review and person browsing, evaluation/export,
administration, and personal settings. Delivered capabilities and outstanding verification are recorded in
[`docs/24-frontend-delivery-plan.md`](docs/24-frontend-delivery-plan.md). The proposed next work is organized in
[`docs/27-frontend-improvement-plan.md`](docs/27-frontend-improvement-plan.md): shared accessibility and
responsive foundations, the agreed global header, individual views, then broader sidebar refinement.
Project switching moves into the sidebar with the header; remaining sidebar work comes last.
The shared-fix batches now implement skip navigation, critical-text contrast, valid shortcut
announcements, canonical product naming, control sizing, responsive fact/workbench layouts, and accessible
contained table scrolling. The third batch adds route-transition focus, reusable inline feedback, and
page/action/content-width conventions. H1 now implements the accepted
[header brief](docs/frontend-header-proposal.md): short breadcrumbs, sidebar project switching, account
menu, and view-owned unsaved-input protection. Signed-out and session-access states now use a compact
public header without an empty sidebar. All 1,235 frontend tests and applicable automated gates pass;
outstanding live browser checks are recorded in the improvement plan. Individual view packages and
broader sidebar work remain pending.
The second active track is operating the stack in production following
[`docs/21-production-promotion.md`](docs/21-production-promotion.md).

Account-level presentation preferences are delivered under
[ADR-0043](docs/decisions/ADR-0043-account-level-user-preferences.md): locale, theme, and explicit desktop
sidebar collapse, owned by the existing local account with revision-checked updates. The backend increment
includes the forward migration, `/api/v1/me/preferences` reads/writes, PostgreSQL/API tests, and generated
transport. The frontend includes the lazy `/settings` page, now reached through the header account
menu, explicit saving and conflict recovery, and saved locale/theme/sidebar application. Private query
state is scoped to the principal; anonymous browser choices remain independent. See the
[delivery sequence](docs/15-implementation-plan.md#account-preferences-increment-adr-0043).

Administrative branding settings are a separate accepted extension under
[ADR-0040](docs/decisions/ADR-0040-administrative-branding-overrides.md). Its backend persistence, reads,
writes, public-branding integration, and revision-protected frontend editing are delivered. Administrative
settings, team administration, and delegated project-membership runtime verification remain pending for
the user's manual testing stage. Scope, sequencing, and acceptance criteria are recorded in
[`docs/15-implementation-plan.md`](docs/15-implementation-plan.md#administrative-settings-increment-adr-0040).
