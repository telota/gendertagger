# ADR-0030: Bilingual client interface with an untranslated canonical vocabulary

**Status:** Accepted

## Context

The browser client is a jointly maintained public-sector tool used by German-speaking editors and by
international collaborators, so its interface must work in German and English. The service also produces a
controlled scientific vocabulary: the four canonical labels (`male`, `female`, `unknown`, `institution`), the
certainty and agreement tiers, and the prediction statuses. These values are written into TEI output,
reported in the published method, and returned by `/api/v1`.

Translating the vocabulary in the interface would create a second name for the same scientific value. The
published method explicitly warns against one such collision: `uncertain` is a certainty tier, while
`unknown` is a label, and the accepted wireframe conflated them. The decision is recorded in
[`24-frontend-delivery-plan.md`](../24-frontend-delivery-plan.md) as D3 and fixes a durable client-boundary
rule alongside [ADR-0006](ADR-0006-vue-browser-client-boundary.md).

## Decision

The interface chrome is internationalised in German and English from the first client milestone, not
retrofitted. All user-facing text lives in message catalogues under `frontend/src/locales/`, one JSON file per
locale, with dot-separated `camelCase` keys grouped by feature.

Canonical labels, tier names, prediction statuses, and identifiers are rendered from their contract token in
every locale and are never part of a catalogue. A translated gloss, where one helps, is a separate catalogue
key shown beside the token and never in place of it. Prose that contains such a token carries `lang="en"` so
assistive technology pronounces it correctly inside a German page.

The rule is enforced mechanically rather than by review:

- a lint rule rejects hard-coded user-facing strings in components;
- `npm run i18n:check` fails on a key missing from any locale, an empty message, or placeholders that differ
  between locales;
- the lint rules of `@intlify/eslint-plugin-vue-i18n` fail on keys that are used but undefined, or defined
  but unused;
- dates and numbers use the i18n library's locale formatting, and sentences are built with named
  interpolation rather than by concatenating translated fragments.

The starting locale is an explicit stored choice, then the first browser language whose primary subtag is
supported, then German. English is the fallback for a missing message so a gap degrades to readable text
instead of a key, while the CI check keeps such gaps from merging.

## Consequences

- Reviewers see one vocabulary for one scientific value in both locales, and screenshots, the paper, and the
  TEI output all use the same words.
- Every screen pays for two catalogues from the start, and layouts must tolerate roughly 35 % text expansion.
  This cost is accepted because retrofitting keys into finished components is the more expensive path.
- The wireframe's fourth action button is relabelled `unknown`, and its `--uncertain*` colour group is renamed
  `--unknown*`, so no interface element names the label after a tier.
- A third locale needs a new catalogue and an entry in the supported-locale list; it does not need a change to
  the vocabulary rule.
- Persisting the locale choice server-side is out of scope, because persisted user settings are excluded from
  the first release. The choice is stored in the browser only.
