import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, onScopeDispose, ref, watch } from 'vue'

import { ApiError, unwrap, type components } from '@/api'
import { useSessionStore } from '@/stores/session'

import { useApiClient } from './useApiClient'

export type UserPreferences = Required<components['schemas']['UserPreferences']>
export type UserPreferencesUpdate = components['schemas']['UserPreferencesUpdate']
export type UserPreferencesSaveResult =
  | { status: 'success'; preferences: UserPreferences }
  | { status: 'conflict' }
  | { status: 'failure'; error: unknown }
  | { status: 'discarded' }

function userPreferencesQueryKey(principalId: string | null) {
  return ['userPreferences', principalId] as const
}

/** The generated response permits omission of the nullable field; its contract default is null. */
function canonicalPreferences(value: components['schemas']['UserPreferences']): UserPreferences {
  return { ...value, locale: value.locale ?? null }
}

/** Account preferences are private query state. Drafts and effective presentation live elsewhere. */
export function useUserPreferences() {
  const client = useApiClient()
  const queryClient = useQueryClient()
  const session = useSessionStore()
  const principalId = computed(() => session.user?.id ?? null)
  const accessState = computed(() => {
    if (session.status === 'idle' || session.status === 'loading' || session.isAuthenticating) {
      return 'loading'
    }
    if (session.status === 'error') return 'sessionError'
    if (principalId.value === null) return 'signedOut'
    if (session.mustChangePassword) return 'passwordChangeRequired'
    return 'eligible'
  })
  const canAccess = computed(() => accessState.value === 'eligible')
  const isSaving = ref(false)
  let epoch = 0
  let disposed = false
  let writeController: AbortController | null = null

  function isCurrent(principal: string | null, requestEpoch: number): boolean {
    return (
      !disposed &&
      principal !== null &&
      canAccess.value &&
      principalId.value === principal &&
      epoch === requestEpoch
    )
  }

  // Sync invalidation also covers A -> B -> A switches before a pending promise resumes.
  watch(
    [principalId, canAccess],
    ([nextPrincipal, eligible], [previousPrincipal]) => {
      epoch += 1
      writeController?.abort()
      writeController = null
      isSaving.value = false
      if (previousPrincipal !== null && (previousPrincipal !== nextPrincipal || !eligible)) {
        const queryKey = userPreferencesQueryKey(previousPrincipal)
        void queryClient.cancelQueries({ queryKey, exact: true })
        queryClient.removeQueries({ queryKey, exact: true })
      }
    },
    { flush: 'sync' },
  )

  const query = useQuery({
    queryKey: computed(() => userPreferencesQueryKey(principalId.value)),
    enabled: canAccess,
    refetchOnWindowFocus: false,
    retry: false,
    queryFn: async ({ signal, queryKey }) => {
      const principal = queryKey[1]
      // Reads belong to the shared query, not the observer whose queryFn started them. A settings
      // view may unmount while the shell still observes it. Account transitions cancel this signal.
      const isCurrentRead = () =>
        !signal.aborted && principal !== null && canAccess.value && principalId.value === principal
      if (!isCurrentRead()) throw new DOMException('Stale account', 'AbortError')
      const saved = await unwrap(client.GET('/api/v1/me/preferences', { signal }))
      if (!isCurrentRead()) throw new DOMException('Stale account', 'AbortError')
      return canonicalPreferences(saved)
    },
  })

  // Query observers update asynchronously; never expose the previous key's data during a switch.
  const preferences = computed(() => {
    if (!query.data.value || !canAccess.value || principalId.value === null) return null
    return (
      queryClient.getQueryData<UserPreferences>(userPreferencesQueryKey(principalId.value)) ?? null
    )
  })

  async function reload(): Promise<UserPreferences | null> {
    const principal = principalId.value
    const requestEpoch = epoch
    if (!isCurrent(principal, requestEpoch) || isSaving.value) return null
    const result = await query.refetch()
    return isCurrent(principal, requestEpoch) && result.isSuccess ? result.data : null
  }

  async function save(command: UserPreferencesUpdate): Promise<UserPreferencesSaveResult> {
    const principal = principalId.value
    const requestEpoch = epoch
    if (!isCurrent(principal, requestEpoch) || isSaving.value) return { status: 'discarded' }
    isSaving.value = true
    const controller = new AbortController()
    writeController = controller
    const queryKey = userPreferencesQueryKey(principal)
    try {
      // A read that started before the save must never replace the canonical PATCH response.
      await queryClient.cancelQueries({ queryKey, exact: true })
      if (!isCurrent(principal, requestEpoch)) return { status: 'discarded' }
      const saved = canonicalPreferences(
        await unwrap(
          client.PATCH('/api/v1/me/preferences', { body: command, signal: controller.signal }),
        ),
      )
      if (!isCurrent(principal, requestEpoch)) return { status: 'discarded' }
      await queryClient.cancelQueries({ queryKey, exact: true })
      if (!isCurrent(principal, requestEpoch)) return { status: 'discarded' }
      queryClient.setQueryData(queryKey, saved)
      return { status: 'success', preferences: saved }
    } catch (error) {
      if (!isCurrent(principal, requestEpoch)) return { status: 'discarded' }
      if (error instanceof ApiError && error.status === 409) return { status: 'conflict' }
      return { status: 'failure', error }
    } finally {
      if (isCurrent(principal, requestEpoch)) {
        isSaving.value = false
        writeController = null
      }
    }
  }

  onScopeDispose(() => {
    disposed = true
    epoch += 1
    writeController?.abort()
  })

  return {
    session,
    principalId,
    accessState,
    canAccess,
    query,
    preferences,
    isSaving,
    save,
    reload,
  }
}
