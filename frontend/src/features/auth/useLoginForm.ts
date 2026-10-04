import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import { useSessionStore } from '@/stores/session'

export interface UseLoginForm {
  username: Ref<string>
  password: Ref<string>
  keepSignedIn: Ref<boolean>
  isSubmitting: Ref<boolean>
  errorMessage: Ref<string | null>
  submitLabel: ComputedRef<string>
  /** Attempts sign-in with the current field values; resolves to whether it succeeded. */
  submit: () => Promise<boolean>
}

function messageFor(t: (key: string) => string, error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'invalid_credentials':
        return t('login.errors.invalidCredentials')
      case 'rate_limited':
        return t('login.errors.rateLimited')
      case 'validation_error':
        return t('login.errors.validation')
      case 'network_error':
        return t('login.errors.network')
    }
  }
  return t('login.errors.generic')
}

/**
 * The username/password/keep-signed-in fields and their submission, shared by the full-page login
 * view and the inline session-recovery prompt. What happens once sign-in succeeds is each caller's
 * own concern (the page navigates on; the recovery prompt just closes and lets the retry proceed).
 */
export function useLoginForm(): UseLoginForm {
  const { t } = useI18n()
  const session = useSessionStore()

  const username = ref('')
  const password = ref('')
  const keepSignedIn = ref(false)
  const isSubmitting = ref(false)
  const errorMessage = ref<string | null>(null)
  const submitLabel = computed(() =>
    isSubmitting.value ? t('login.submitting') : t('login.submit'),
  )

  watch(
    () => session.principalRevision,
    () => {
      password.value = ''
      errorMessage.value = null
    },
    { flush: 'sync' },
  )

  async function submit(): Promise<boolean> {
    errorMessage.value = null
    isSubmitting.value = true
    try {
      await session.login({
        username: username.value,
        password: password.value,
        keepSignedIn: keepSignedIn.value,
      })
      password.value = ''
      return true
    } catch (error) {
      errorMessage.value = messageFor(t, error)
      return false
    } finally {
      isSubmitting.value = false
    }
  }

  return { username, password, keepSignedIn, isSubmitting, errorMessage, submitLabel, submit }
}
