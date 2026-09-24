<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
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
    await router.push(redirectTarget())
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
    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('changePassword.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="change-password-load-error">
      <p role="alert">{{ t('changePassword.loadError') }}</p>
      <AppButton type="button" @click="retry">{{ t('changePassword.retry') }}</AppButton>
    </div>
    <template v-else-if="session.isSignedIn">
      <p class="change-password-notice">{{ t('changePassword.notice') }}</p>
      <form class="change-password-form" novalidate @submit.prevent="submit">
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

.change-password-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

.change-password-load-error p {
  margin: 0;
  color: var(--critical);
}

.change-password-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

.change-password-error {
  margin: 0;
  color: var(--critical);
}
</style>
