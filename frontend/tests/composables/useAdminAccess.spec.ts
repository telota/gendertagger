import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { useAdminAccess } from '@/composables/useAdminAccess'
import type { CurrentUser } from '@/stores/session'

const ADMIN: CurrentUser = {
  id: 'a0000000-0000-0000-0000-000000000001',
  display_name: 'Admin',
  roles: ['admin'],
}

describe('administrative authentication eligibility', () => {
  it.each([false, true])(
    'waits for replacement flags (password change required: %s)',
    async (required) => {
      let resolveFlags!: (response: Response) => void
      const flags = new Promise<Response>((resolve) => {
        resolveFlags = resolve
      })
      const client = createApiClient({
        fetch: async (request) =>
          new URL(request.url).pathname === '/api/v1/auth/login' ? Response.json(ADMIN) : flags,
      })
      let access!: ReturnType<typeof useAdminAccess>
      const wrapper = mount(
        defineComponent({
          setup() {
            access = useAdminAccess()
            return () => null
          },
        }),
        {
          global: { plugins: [createPinia()], provide: { [API_CLIENT_KEY as symbol]: client } },
        },
      )
      access.session.user = { ...ADMIN, id: 'a0000000-0000-0000-0000-000000000002' }
      access.session.status = 'ready'
      expect(access.canAccessAdmin.value).toBe(true)

      const login = access.session.login({
        username: 'admin',
        password: 'correct',
        keepSignedIn: false,
      })
      await flushPromises()
      expect(access.session.user).toEqual(ADMIN)
      expect(access.state.value).toBe('loading')
      expect(access.canAccessAdmin.value).toBe(false)

      resolveFlags(Response.json({ must_change_password: required, keep_signed_in: false }))
      await login
      expect(access.state.value).toBe(required ? 'passwordChangeRequired' : 'eligible')
      expect(access.canAccessAdmin.value).toBe(!required)
      wrapper.unmount()
    },
  )
})
