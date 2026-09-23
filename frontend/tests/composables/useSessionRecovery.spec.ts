import { describe, expect, it } from 'vitest'

import { requestReauthentication, useSessionRecovery } from '@/composables/useSessionRecovery'

describe('useSessionRecovery', () => {
  it('opens the prompt and resolves the waiting request once the user signs in again', async () => {
    const recovery = useSessionRecovery()
    expect(recovery.isOpen.value).toBe(false)

    const pending = requestReauthentication()
    expect(recovery.isOpen.value).toBe(true)

    recovery.resolve()

    await expect(pending).resolves.toBeUndefined()
    expect(recovery.isOpen.value).toBe(false)
  })

  it('rejects the waiting request and closes the prompt when the user declines', async () => {
    const recovery = useSessionRecovery()
    const reason = new Error('declined')

    const pending = requestReauthentication()
    recovery.reject(reason)

    await expect(pending).rejects.toBe(reason)
    expect(recovery.isOpen.value).toBe(false)
  })

  it('settles every request that arrived while the prompt was already open, together', async () => {
    const recovery = useSessionRecovery()

    const first = requestReauthentication()
    const second = requestReauthentication()
    recovery.resolve()

    await expect(Promise.all([first, second])).resolves.toEqual([undefined, undefined])
  })

  it('does not resettle a request from a prompt that already closed', async () => {
    const recovery = useSessionRecovery()
    const first = requestReauthentication()
    recovery.resolve()
    await first

    // A later, unrelated recovery must not touch the already-settled first waiter.
    const second = requestReauthentication()
    recovery.reject(new Error('declined'))

    await expect(second).rejects.toThrow('declined')
  })
})
