import { useQuery, type QueryClient } from '@tanstack/vue-query'
import { computed, type ComputedRef } from 'vue'

import { unwrap, type ApiClient, type components } from '@/api'

import { useApiClient } from './useApiClient'

type RawBrandingInfo = components['schemas']['BrandingInfo']
type BrandingInitiative = components['schemas']['BrandingInitiative']
type RawBrandingLegalEntity = components['schemas']['BrandingLegalEntity']

const BRANDING_QUERY_KEY = ['branding'] as const

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
  state: ComputedRef<BrandingState>
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

function brandingQueryOptions(client: ApiClient) {
  return {
    queryKey: BRANDING_QUERY_KEY,
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      unwrap(client.GET('/api/v1/branding', { signal })).then(normalize),
  }
}

/**
 * Refresh public branding after a confirmed administrative write. Cancelling an in-flight read first
 * prevents a response that started before the write from overwriting the server-confirmed refresh.
 */
export async function refreshPublicBranding(
  queryClient: QueryClient,
  client: ApiClient,
): Promise<BrandingInfo> {
  await queryClient.cancelQueries({ queryKey: BRANDING_QUERY_KEY })
  return queryClient.fetchQuery(brandingQueryOptions(client))
}

/**
 * Shared unauthenticated public branding. The public cache intentionally contains only `BrandingInfo`;
 * administrative revision and override metadata remain in a separate principal-scoped query.
 */
export function useBranding(client: ApiClient = useApiClient()): UseBranding {
  const query = useQuery(brandingQueryOptions(client))
  const state = computed<BrandingState>(() => {
    if (query.isPending.value) return { status: 'loading' }
    if (query.isError.value) return { status: 'error' }
    const data = query.data.value
    return data === undefined ? { status: 'loading' } : { status: 'ready', data }
  })

  async function refresh(): Promise<void> {
    await query.refetch()
  }

  return { state, refresh }
}
