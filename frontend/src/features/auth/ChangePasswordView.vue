<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useSessionStore } from '@/stores/session'

const MIN_PASSWORD_LENGTH = 12

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const session = useSessionStore()

const currentPassword = ref('')
const newPassword = ref('')
const repeatNewPassword = ref('')
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)
const submitLabel = computed(() =>
  isSubmitting.value ? t('changePassword.submitting') : t('changePassword.submit'),
)

watch(
  () => session.principalRevision,
  () => {
    currentPassword.value = ''
    newPassword.value = ''
    repeatNewPassword.value = ''
    errorMessage.value = null
    isSubmitting.value = false
  },
  { flush: 'sync' },
)

// App.vue's session.initialize() is still resolving on a fresh page load; deciding from
// session.isSignedIn before it settles would bounce an actually-signed-in visitor to /login.
// Wait for the one 'loading' -> 'ready' transition instead of reading the flag immediately.
watch(
  () => session.status,
  (status) => {
    if (status === 'ready' && !session.isSignedIn) void router.replace({ name: 'login' })
  },
  { immediate: true },
)

function retry(): void {
  void session.initialize()
}
function redirectTarget(): string {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/'
}

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'invalid_current_password':
        return t('changePassword.errors.invalidCurrentPassword')
      case 'validation_error':
        return t('changePassword.errors.validation', { minLength: String(MIN_PASSWORD_LENGTH) })
      case 'network_error':
        return t('changePassword.errors.network')
    }
  }
  return t('changePassword.errors.generic')
}

async function submit(): Promise<void> {
  const revision = session.principalRevision
  errorMessage.value = null
  if (newPassword.value !== repeatNewPassword.value) {
    errorMessage.value = t('changePassword.errors.mismatch')
    return
  }
  isSubmitting.value = true
  try {
    await session.changePassword({
      currentPassword: currentPassword.value,
      newPassword: newPassword.value,
    })
    if (revision !== session.principalRevision) return
    await router.push(redirectTarget())
  } catch (error) {
    if (revision === session.principalRevision) errorMessage.value = messageFor(error)
  } finally {
    if (revision === session.principalRevision) isSubmitting.value = false
  }
}
</script>

<template>
  <main class="change-password app-page-frame app-page-frame--auth">
    <header class="change-password-heading app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="change-password-title app-page-heading__title">
          {{ t('changePassword.title') }}
        </h1>
        <p
          v-if="session.status === 'ready' && session.isSignedIn"
          class="change-password-notice app-page-heading__description"
        >
          {{ t('changePassword.notice') }}
        </p>
      </div>
    </header>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="app-card"
      announcement="polite"
    >
      {{ t('changePassword.loading') }}
    </AppFeedback>
    <AppFeedback
      v-else-if="session.status === 'error'"
      class="change-password-load-error app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('changePassword.loadError') }}
      <template #actions>
        <AppButton type="button" variant="ghost" @click="retry">
          {{ t('changePassword.retry') }}
        </AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="session.isSignedIn">
      <form class="change-password-form app-card" novalidate @submit.prevent="submit">
        <AppTextField
          id="change-password-current"
          v-model="currentPassword"
          name="current-password"
          type="password"
          :label="t('changePassword.current')"
          autocomplete="current-password"
          required
        />
        <AppTextField
          id="change-password-new"
          v-model="newPassword"
          name="new-password"
          type="password"
          :label="t('changePassword.new')"
          autocomplete="new-password"
          :minlength="MIN_PASSWORD_LENGTH"
          required
        />
        <AppTextField
          id="change-password-repeat"
          v-model="repeatNewPassword"
          name="new-password-repeat"
          type="password"
          :label="t('changePassword.repeat')"
          autocomplete="new-password"
          :minlength="MIN_PASSWORD_LENGTH"
          required
        />
        <p v-if="errorMessage" role="alert" class="change-password-error">{{ errorMessage }}</p>
        <AppButton type="submit" :disabled="isSubmitting">{{ submitLabel }}</AppButton>
      </form>
    </template>
  </main>
</template>

<style scoped>
.change-password-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

.change-password-error {
  margin: 0;
  color: var(--critical-text);
}
</style>
