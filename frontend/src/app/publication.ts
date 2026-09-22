// Everything the BBAW guideline for digital publications requires — editors, publisher, contact,
// initiatives, legal-notice provider details — is operator-configured deployment data, served by
// the backend over GET /api/v1/branding (ADR-0036) and consumed through useBranding(), never a
// frontend constant.
//
// The one exception is the software's own source-code licence: it is the same for every
// deployment of this codebase, so it is not part of that configuration.

/**
 * The licence of the application source code (LICENSE), not of any register data.
 *
 * The copyright holder is whoever wrote the code, per LICENSE — fixed for every deployment,
 * unlike the operating institution in `branding.institution_name`, which can differ from it.
 */
export const SOURCE_CODE_LICENSE = {
  name: 'MIT',
  url: 'https://opensource.org/license/mit',
  copyrightYear: 2026,
  copyrightHolder: 'TELOTA – The Electronic Life Of The Academy',
} as const
