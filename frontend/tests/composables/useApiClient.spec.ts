import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import type { ApiClient } from '@/api'
import { API_CLIENT_KEY, useApiClient } from '@/composables/useApiClient'

function mountWithApiClient(provided?: ApiClient) {
  let resolved!: ApiClient
  mount(
    defineComponent({
      setup() {
        resolved = useApiClient()
        return () => null
      },
    }),
    {
      global: provided ? { provide: { [API_CLIENT_KEY as symbol]: provided } } : {},
    },
  )
  return resolved
}

describe('useApiClient', () => {
  it('returns the provided client when the application has provided one', () => {
    const provided = {} as ApiClient

    expect(mountWithApiClient(provided)).toBe(provided)
  })

  it('falls back to a default client when nothing was provided', () => {
    expect(mountWithApiClient()).toBeDefined()
  })
})
