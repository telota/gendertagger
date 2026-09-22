<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppTextField from '@/components/base/AppTextField.vue'
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
      <AppTextField
        id="login-username"
        v-model="username"
        name="username"
        :label="t('login.username')"
        autocomplete="username"
        required
      />
      <AppTextField
        id="login-password"
        v-model="password"
        name="password"
        type="password"
        :label="t('login.password')"
        autocomplete="current-password"
        required
      />
      <div class="login-checkbox">
        <input id="login-keep-signed-in" v-model="keepSignedIn" type="checkbox" />
        <label for="login-keep-signed-in">{{ t('login.keepSignedIn') }}</label>
      </div>
      <p v-if="errorMessage" role="alert" class="login-error">{{ errorMessage }}</p>
      <AppButton type="submit" :disabled="isSubmitting">{{ submitLabel }}</AppButton>
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
  align-items: flex-start;
  gap: var(--space-4);
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
</style>
