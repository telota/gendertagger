<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api'
import { useSessionStore } from '@/stores/session'

const MIN_PASSWORD_LENGTH = 12

const { t } = useI18n()
const router = useRouter()
const session = useSessionStore()

const currentPassword = ref('')
const newPassword = ref('')
const repeatNewPassword = ref('')
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)
const submitLabel = computed(() =>
  isSubmitting.value ? t('changePassword.submitting') : t('changePassword.submit'),
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
    await router.push({ name: 'home' })
  } catch (error) {
    errorMessage.value = messageFor(error)
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="change-password">
    <h1 class="change-password-title">{{ t('changePassword.title') }}</h1>
    <p v-if="session.status !== 'ready'" role="status">{{ t('changePassword.loading') }}</p>
    <template v-else-if="session.isSignedIn">
      <p class="change-password-notice">{{ t('changePassword.notice') }}</p>
      <form class="change-password-form" novalidate @submit.prevent="submit">
        <div class="change-password-field">
          <label for="change-password-current">{{ t('changePassword.current') }}</label>
          <input
            id="change-password-current"
            v-model="currentPassword"
            name="current-password"
            type="password"
            autocomplete="current-password"
            required
          />
        </div>
        <div class="change-password-field">
          <label for="change-password-new">{{ t('changePassword.new') }}</label>
          <input
            id="change-password-new"
            v-model="newPassword"
            name="new-password"
            type="password"
            autocomplete="new-password"
            :minlength="MIN_PASSWORD_LENGTH"
            required
          />
        </div>
        <div class="change-password-field">
          <label for="change-password-repeat">{{ t('changePassword.repeat') }}</label>
          <input
            id="change-password-repeat"
            v-model="repeatNewPassword"
            name="new-password-repeat"
            type="password"
            autocomplete="new-password"
            :minlength="MIN_PASSWORD_LENGTH"
            required
          />
        </div>
        <p v-if="errorMessage" role="alert" class="change-password-error">{{ errorMessage }}</p>
        <button type="submit" class="change-password-submit" :disabled="isSubmitting">
          {{ submitLabel }}
        </button>
      </form>
    </template>
  </main>
</template>

<style scoped>
.change-password {
  flex: 1;
  width: 100%;
  max-width: 24rem;
  margin: 0 auto;
  padding: var(--space-12) var(--space-4);
}

.change-password-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}

.change-password-notice {
  margin: 0 0 var(--space-6);
  color: var(--text-secondary);
}

.change-password-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.change-password-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.change-password-field label {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}

.change-password-field input {
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  padding: var(--space-2) var(--space-3);
}

.change-password-error {
  margin: 0;
  color: var(--critical);
}

.change-password-submit {
  align-self: flex-start;
  border: 1px solid var(--accent-b);
  border-radius: var(--radius-control);
  background: var(--accent-b);
  color: var(--panel);
  font: inherit;
  font-weight: var(--weight-semibold);
  padding: var(--space-2) var(--space-4);
  cursor: pointer;
}

.change-password-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
