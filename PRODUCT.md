# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary users are editorial reviewers working through person-register cases in sustained review sessions. They need to resolve uncertain or conflicting classifications quickly while keeping the underlying evidence, uncertainty, source record, and decision history visible.

Project operators manage the reproducible pipeline: import source registers, select and configure methods, run classification, aggregate results, evaluate methods, and export reviewed data. Administrators manage local accounts, teams, project membership, and deployment-specific publication metadata.

## Product Purpose

gendertagger is a local-first, human-in-the-loop service for enriching TEI/XML person registers with gender annotations. It combines multiple independent classification methods, preserves disagreement and missing evidence, supports append-only editorial review, and produces evaluations and provenance-preserving exports.

Success balances three outcomes: trustworthy review throughput, end-to-end reproducibility, and operational self-service for research teams.

## Positioning

gendertagger is a public scholarly workbench rather than a generic gender-prediction interface. Its distinctive mechanism is the combination of independent methods, uncertainty-aware aggregation, visible source and method evidence, append-only human decisions, and reproducible provenance from import through export. It supports local and private operation instead of requiring external hosted services.

## Operating Context

The product combines an authenticated browser workbench with a public publication shell. Editorial reviewers use the review queue and person browser; operators move projects through import, classification, aggregation, evaluation, and export; administrators maintain access and institutional publication settings.

The interface is German and English. Scientific vocabulary, identifiers, hashes, source locations, and provenance are working material rather than implementation detail. Deployments may provide their own institution, editors, initiatives, legal entity, contact, privacy notice, publication period, and logo.

## Capabilities and Constraints

- A person is identified by TEI `xml:id` within a project; the product does not invent a global person identity.
- `male`, `female`, `unknown`, and `institution` are canonical labels. `unknown`, method abstention, and technical error remain distinct.
- Method confidence values are method-specific and are never presented as globally calibrated probabilities, combined into one score, or used as a review threshold.
- Predictions and successful dataset snapshots are immutable. Human annotations are append-only decisions; later decisions supersede earlier ones without rewriting history.
- Imports, runs, aggregations, evaluations, and exports remain reproducible from persisted configuration and provenance.
- Long-running resources expose their own lifecycle and failures. Collections are filtered, sorted, and cursor-paginated by the server.
- The Vue client consumes the versioned HTTP API and does not duplicate scientific or persistence logic.
- Authorization is role-scoped and server-authoritative. The interface may explain capabilities but never substitutes presentation rules for authorization.
- Public-facing facts come from deployment branding configuration. The interface must not fabricate institution, publisher, editor, legal, benchmark, or performance claims.
- Open product decision: stakeholders still need to confirm the documented v1 exclusions, including Git repository synchronization, activity notifications, game mode, persisted user/project settings, bulk API writes, and per-case timing telemetry.

## Brand Commitments

The product name is gendertagger. Its voice is precise, neutral, and evidence-led. It explains uncertainty and recovery without blaming the user or overstating what automated methods know.

Canonical labels, tier names, status values, and identifiers remain English tokens in both interface locales; explanatory interface copy is translated. Institutional identity is configurable per deployment and is not hard-coded as the product identity.

## Evidence on Hand

- Product and scientific contract: `SPEC.md`, `AGENTS.md`, and the architecture documents under `docs/`.
- Existing interaction and content requirements: `docs/23-wireframe-ui-inventory.md`, `docs/24-frontend-delivery-plan.md`, and `docs/25-frontend-design-guidelines.md`.
- Existing production-shaped Vue interface: `frontend/src/`.
- Representative development data covering lifecycle, error, uncertainty, conflict, review-history, evaluation, and export states: `backend/scripts/seed_frontend_development.py` and the frontend fixtures under `frontend/tests/`.
- A published reference workflow and evaluation definitions exist in the repository; future interface claims must remain traceable to those sources.
- The current development deployment has no configured institutional publication facts or logo. Future work must keep the explicit unconfigured state rather than inventing them.

## Product Principles

1. Make evidence and uncertainty legible before making the interface look conclusive.
2. Keep the primary review path fast without hiding provenance or weakening the audit trail.
3. Preserve reproducibility across every transition from source import to reviewed export.
4. Let research teams operate the system themselves while keeping permissions and destructive changes explicit.
5. Treat accessibility, bilingual content, and publication accountability as product requirements, not finishing work.

## Accessibility & Inclusion

WCAG 2.2 AA is a binding target for this public scholarly workbench. Every screen must support keyboard-only use, visible focus, meaningful screen-reader output, 400% zoom and reflow to 320 CSS px without page-level horizontal scrolling, browser text-spacing overrides, and reduced-motion preferences.

German and English must both fit without lost meaning or clipped actions. Status, label, certainty, agreement, and error distinctions cannot rely on colour alone. At least one user-testing round with people with disabilities and a named accessibility owner remain required before public release, alongside confirmation of the applicable accessibility statement and feedback mechanism.
