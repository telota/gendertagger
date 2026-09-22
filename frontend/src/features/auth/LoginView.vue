<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const username = ref('')
const password = ref('')
const keepSignedIn = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)
const submitLabel = computed(() => (isSubmitting.value ? t('login.submitting') : t('login.submit')))

function messageFor(error: unknown): string {
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

function redirectTarget(): string {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/'
}

async function submit(): Promise<void> {
  errorMessage.value = null
  isSubmitting.value = true
  try {
    await session.login({
      username: username.value,
      password: password.value,
      keepSignedIn: keepSignedIn.value,
    })
    await router.push(session.mustChangePassword ? { name: 'changePassword' } : redirectTarget())
  } catch (error) {
    errorMessage.value = messageFor(error)
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="login">
    <h1 class="login-title">{{ t('login.title') }}</h1>
    <form class="login-form" novalidate @submit.prevent="submit">
      <div class="login-field">
        <label for="login-username">{{ t('login.username') }}</label>
        <input
          id="login-username"
          v-model="username"
          name="username"
          type="text"
          autocomplete="username"
          required
        />
      </div>
      <div class="login-field">
        <label for="login-password">{{ t('login.password') }}</label>
        <input
          id="login-password"
          v-model="password"
          name="password"
          type="password"
          autocomplete="current-password"
          required
        />
      </div>
      <div class="login-checkbox">
        <input id="login-keep-signed-in" v-model="keepSignedIn" type="checkbox" />
        <label for="login-keep-signed-in">{{ t('login.keepSignedIn') }}</label>
      </div>
      <p v-if="errorMessage" role="alert" class="login-error">{{ errorMessage }}</p>
      <button type="submit" class="login-submit" :disabled="isSubmitting">
        {{ submitLabel }}
      </button>
    </form>
  </main>
</template>

<style scoped>
.login {
  flex: 1;
  width: 100%;
  max-width: 24rem;
  margin: 0 auto;
  padding: var(--space-12) var(--space-4);
}

.login-title {
  margin: 0 0 var(--space-6);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.login-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.login-field label {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}

.login-field input {
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  padding: var(--space-2) var(--space-3);
}

.login-checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.login-checkbox label {
  font-size: var(--font-size-small);
}

.login-error {
  margin: 0;
  color: var(--critical);
}

.login-submit {
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

.login-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
