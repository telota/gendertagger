<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useSessionStore } from '@/stores/session'

import { signInDestination } from './signInDestination'
import { useLoginForm } from './useLoginForm'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const {
  username,
  password,
  keepSignedIn,
  isSubmitting,
  errorMessage,
  submitLabel,
  submit: attemptLogin,
} = useLoginForm()

function redirectTarget(): string {
  const redirect = route.query.redirect
  return typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/'
}

async function submit(): Promise<void> {
  const succeeded = await attemptLogin()
  if (succeeded) {
    await router.push(signInDestination(session.mustChangePassword, redirectTarget()))
  }
}
</script>

<template>
  <main class="login app-page-frame app-page-frame--auth">
    <header class="login-heading app-page-heading">
      <h1 class="login-title app-page-heading__title">{{ t('login.title') }}</h1>
    </header>
    <form class="login-form app-card" novalidate @submit.prevent="submit">
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
  color: var(--critical-text);
}
</style>
