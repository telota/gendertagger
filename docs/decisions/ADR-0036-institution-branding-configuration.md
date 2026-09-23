# ADR-0036: Institution branding is deployment configuration served by the backend

**Status:** Accepted

## Context

The client must carry the publication, footer, and legal-notice information required by the BBAW guideline
for digital publications, mapped in
[`25-frontend-design-guidelines.md`](../25-frontend-design-guidelines.md#publication-details-footer-and-legal-notice):
the publisher's name and logo, editors, publication period, institutional context, a contact address, the
source-code licence, a privacy-notice link, and a legal notice modelled on `bbaw.de/impressum` with the
provider's address, telephone, representative, and VAT identification number.

An initial implementation hard-coded these as TypeScript literals in the frontend, built into the bundle. That
implementation was reverted before merge because gendertagger is not exclusively a BBAW tool: `PLAN.md` and
`SPEC.md` describe a general-purpose service, the reference corpus in this repository belongs to a different
edition (`schleiermacher digital`), and nothing else in the codebase assumes a single institutional operator.
Baking one institution's legal identity into the bundle would make every other deployment either ship BBAW's
name on its own legal notice or fork the frontend to change it.

The deployment model rules out a build-time fix. [`21-production-promotion.md`](../21-production-promotion.md)
pulls one immutable tagged image through every environment; CI builds that image once per commit
([`.gitlab-ci.yml`](../../.gitlab-ci.yml) `build_and_publish_frontend`). A second operator deploying the same
tag cannot rebuild it with their own institutional facts baked in, so those facts cannot live in the built
JavaScript.

The backend already solves exactly this problem for every other piece of deployment-specific configuration:
`AppSettings` ([`api/settings.py`](../../backend/src/gendertagger/api/settings.py)) reads validated
`GENDERTAGGER_*` environment variables at process start, so an operator configures a deployment by setting
variables, not by rebuilding an image. Rule 2 of [`AGENTS.md`](../../AGENTS.md) also makes FastAPI the
canonical public interface; a second, frontend-only configuration channel (for example, an nginx
`docker-entrypoint.d` script rendering a JSON file with `envsubst`) would duplicate that mechanism for no
reason other than which process happens to render the value.

## Decision

Institution branding is operator-supplied deployment configuration, read once at backend process start like
every other `AppSettings` value, and served to the browser over an unauthenticated `/api/v1` endpoint. It is
never a frontend build input and never hard-coded for one institution.

**Settings.** `AppSettings` gains a nested, optional `branding` configuration
(`GENDERTAGGER_BRANDING__*`, pydantic-settings' nested-delimiter convention) with:

- `institution_name: str | None`, `institution_url: str | None`
- `logo_path: Path | None` — a file the deployment mounts into the backend container; unset means no logo
- `editors: list[str]`, `published_since_year: int | None`
- `initiatives: list[{name: str, url: str}]` — proper names such as an affiliated lab or programme, shown
  untranslated; empty by default
- `contact_email: str | None`, `privacy_notice_url: str | None`
- `legal_entity: {name, legal_form, address_lines: list[str], telephone, telephone_href, representative,
  vat_id} | None`

Every field is optional and defaults to absent. An unconfigured deployment runs with an empty legal notice
rather than failing to start, because the fields are only needed once an operator exposes the service
publicly, which is exactly when they must be set.

**Endpoint.** `GET /api/v1/branding` returns a `BrandingInfo` built from these settings, through the same
unauthenticated router as `POST /auth/login` ([ADR-0031](ADR-0031-local-database-authentication.md)) — the
legal notice must be reachable without a session. A field left unset by the operator is `null` in the
response; the frontend renders that as an explicit "not configured" state per an absent field, never
invented text, matching the existing design principle "nothing is invented"
([`25-frontend-design-guidelines.md`](../25-frontend-design-guidelines.md)).

**Logo.** `GET /api/v1/branding/logo` streams the file at `logo_path` with its detected media type, or `404`
when unset or missing. `BrandingInfo.logo_url` is the literal string `"/api/v1/branding/logo"` when the file
exists and `null` otherwise, so the frontend never constructs the path itself and never needs an absolute
external URL — keeping the logo same-origin, per the frontend security rule against loading assets from
another origin ([`26-frontend-coding-guidelines.md`](../26-frontend-coding-guidelines.md)).

**Frontend.** The footer, the start page's publication block, and `/impressum` fetch `GET /api/v1/branding`
like any other transport call (generated types, same error handling) instead of importing a local module of
constants. No branding fact is a TypeScript literal.

**This deployment's values.** BBAW's own facts (name, address, representative, VAT ID, `telota@bbaw.de`, the
KI-Lab and Gender & Data links) are operational configuration for this specific deployment, set through its
environment (for example `compose.prod.yaml` or a deployment-local `.env`), not through source code. They are
recorded in [`25-frontend-design-guidelines.md`](../25-frontend-design-guidelines.md) as the values this
deployment configures, not as defaults the software ships with.

## Consequences

- The same tagged image serves any institution; branding changes are a configuration change and a process
  restart, never a rebuild.
- The legal notice can legitimately be empty on an unconfigured deployment (a local checkout, a CI review
  app). That is correct: an empty notice is honest, while a hard-coded one would misrepresent who operates
  that instance.
- One more unauthenticated, versioned surface joins `POST /auth/login`; it carries no scientific or
  project-scoped data, so it needs no role check, matching `GET /methods` and `POST /classify`'s "any grant"
  precedent only in that it is equally free of project data — unlike those, it needs no grant at all.
- The frontend loses the option of rendering the footer before any network round trip completes. This is
  already true of every other screen behind the session check, so it adds no new failure mode, but the footer
  needs its own loading/absent state per the interface-states table.
- A future second operator's deployment guide gains one section: set `GENDERTAGGER_BRANDING__*` and mount a
  logo file, instead of "edit and rebuild the frontend."
- Rejected: an nginx `docker-entrypoint.d` script rendering a static JSON file with `envsubst`. It would work,
  but it duplicates `AppSettings` as a second, frontend-only configuration channel and needs its own
  validation, whereas the backend's is already tested and typed.
- Rejected: keeping the BBAW facts as frontend defaults with an override mechanism. A default that is one
  institution's legal identity is exactly the coupling this decision removes; an unconfigured value must be
  absent, not BBAW's.
- Follow-up: `GET /api/v1/branding` and `GET /api/v1/branding/logo` need entries in
  [`05-api.md`](../05-api.md) and the OpenAPI snapshot when implemented, and the reverted frontend work in
  branch `wip/publication-footer-legal-notice` needs rebuilding against this endpoint rather than
  `src/app/publication.ts`.
