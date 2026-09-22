import { inject, type InjectionKey } from 'vue'

import { createApiClient, type ApiClient } from '@/api'

/** Provided once by `bootstrap.ts`; overridable per test with `global.provide`. */
export const API_CLIENT_KEY: InjectionKey<ApiClient> = Symbol('apiClient')

/** The application's one typed HTTP client (docs/26-frontend-coding-guidelines.md). */
export function useApiClient(): ApiClient {
  return inject(API_CLIENT_KEY) ?? createApiClient()
}
