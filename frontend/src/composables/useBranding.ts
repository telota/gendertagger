import { onMounted, ref, type Ref } from 'vue'

import { unwrap, type ApiClient, type components } from '@/api'

import { useApiClient } from './useApiClient'

type RawBrandingInfo = components['schemas']['BrandingInfo']
type BrandingInitiative = components['schemas']['BrandingInitiative']
type RawBrandingLegalEntity = components['schemas']['BrandingLegalEntity']

/**
 * `GET /api/v1/branding` (ADR-0036) with every collection field normalized to a guaranteed array.
 *
 * The generated type makes every field optional, because every one has a default on the backend;
 * an absent array and an empty array carry the same meaning, "nothing configured", so this
 * normalization loses no information and keeps templates free of `?? []` at every use site.
 */
export interface BrandingInfo extends Omit<
  RawBrandingInfo,
  'editors' | 'initiatives' | 'legal_entity'
> {
  editors: string[]
  initiatives: BrandingInitiative[]
  legal_entity: BrandingLegalEntity | null
}

export interface BrandingLegalEntity extends Omit<RawBrandingLegalEntity, 'address_lines'> {
  address_lines: string[]
}

export type BrandingState =
  { status: 'loading' } | { status: 'ready'; data: BrandingInfo } | { status: 'error' }

export interface UseBranding {
  state: Ref<BrandingState>
  /** Re-fetch, e.g. from a retry affordance after `status === 'error'`. */
  refresh: () => Promise<void>
}

function normalize(raw: RawBrandingInfo): BrandingInfo {
  return {
    institution_name: raw.institution_name ?? null,
    institution_url: raw.institution_url ?? null,
    logo_url: raw.logo_url ?? null,
    editors: raw.editors ?? [],
    published_since_year: raw.published_since_year ?? null,
    initiatives: raw.initiatives ?? [],
    contact_email: raw.contact_email ?? null,
    privacy_notice_url: raw.privacy_notice_url ?? null,
    legal_entity: raw.legal_entity ? normalizeLegalEntity(raw.legal_entity) : null,
  }
}

function normalizeLegalEntity(raw: RawBrandingLegalEntity): BrandingLegalEntity {
  return {
    name: raw.name,
    legal_form: raw.legal_form ?? null,
    address_lines: raw.address_lines ?? [],
    telephone: raw.telephone ?? null,
    telephone_href: raw.telephone_href ?? null,
    representative: raw.representative ?? null,
    vat_id: raw.vat_id ?? null,
  }
}

/**
 * Fetch this deployment's branding (ADR-0036) once for the calling component.
 *
 * A deliberate stand-in for the shared server-state query/cache layer that arrives with the M2
 * shell (docs/26-frontend-coding-guidelines.md): every caller fetches independently rather than
 * sharing one cached request. `GET /api/v1/branding` is small, unauthenticated, and cheap, so
 * fetching it once per mounted footer, start page, and legal notice is an acceptable
 * simplification until that layer exists.
 */
export function useBranding(client: ApiClient = useApiClient()): UseBranding {
  const state = ref<BrandingState>({ status: 'loading' })

  async function refresh(): Promise<void> {
    state.value = { status: 'loading' }
    try {
      const data = normalize(await unwrap(client.GET('/api/v1/branding')))
      state.value = { status: 'ready', data }
    } catch {
      // The footer and start page degrade to their unconfigured treatment on error; the legal
      // notice page, where branding is the page's own content, surfaces this status itself.
      state.value = { status: 'error' }
    }
  }

  onMounted(refresh)

  return { state, refresh }
}
