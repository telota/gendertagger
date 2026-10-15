<script setup lang="ts">
import { PhSignIn } from '@phosphor-icons/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { signInDestination } from '@/features/auth/signInDestination'
import { useLoginForm } from '@/features/auth/useLoginForm'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
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

const steps = computed(() => [
  {
    key: 'import',
    title: t('home.guest.steps.importTitle'),
    text: t('home.guest.steps.importText'),
  },
  {
    key: 'classify',
    title: t('home.guest.steps.classifyTitle'),
    text: t('home.guest.steps.classifyText'),
  },
  {
    key: 'review',
    title: t('home.guest.steps.reviewTitle'),
    text: t('home.guest.steps.reviewText'),
  },
])

// Signing in here skips the welcome view and continues straight to the signed-in home page (D26:
// the project list/hub the visitor came for lives there now, not at the separate `/projects` page).
async function submit(): Promise<void> {
  if (await attemptLogin()) {
    await router.push(signInDestination(session.mustChangePassword, '/'))
  }
}
</script>

<template>
  <div class="home-guest">
    <header class="home-guest-heading app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="home-guest-lede app-page-heading__title">{{ t('home.guest.lede') }}</h1>
        <p class="home-guest-intro app-page-heading__description">{{ t('home.guest.intro') }}</p>
      </div>
    </header>

    <form
      class="home-guest-signin app-card"
      novalidate
      :aria-label="t('login.title')"
      @submit.prevent="submit"
    >
      <div class="home-guest-signin-row">
        <AppTextField
          id="home-username"
          v-model="username"
          class="home-guest-signin-field"
          name="username"
          :label="t('login.username')"
          autocomplete="username"
          required
        />
        <AppTextField
          id="home-password"
          v-model="password"
          class="home-guest-signin-field"
          name="password"
          type="password"
          :label="t('login.password')"
          autocomplete="current-password"
          required
        />
        <AppButton type="submit" :disabled="isSubmitting">
          <PhSignIn :size="18" aria-hidden="true" />
          {{ submitLabel }}
        </AppButton>
      </div>
      <div class="home-guest-signin-keep">
        <input id="home-keep-signed-in" v-model="keepSignedIn" type="checkbox" />
        <label for="home-keep-signed-in">{{ t('login.keepSignedIn') }}</label>
      </div>
      <p v-if="errorMessage" role="alert" class="home-guest-signin-error">{{ errorMessage }}</p>
      <p class="home-guest-account-hint">{{ t('home.guest.accountHint') }}</p>
    </form>

    <ol
      class="home-guest-steps app-card app-card--sectioned"
      :aria-label="t('home.guest.stepsLabel')"
    >
      <li v-for="step in steps" :key="step.key" class="home-guest-step">
        <span class="home-guest-step-title">{{ step.title }}</span>
        <span class="home-guest-step-text">{{ step.text }}</span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.home-guest {
  display: flex;
  flex-direction: column;
}

/* German compounds ("Geschlechtsangaben", "Personenregister") otherwise wrap whole and leave a ragged
   right edge; the document language follows the locale, so this hyphenates German and English alike. */
.home-guest-lede,
.home-guest-intro,
.home-guest-step-text {
  hyphens: auto;
  hyphenate-limit-chars: 7 3 3;
}

.home-guest-lede {
  text-wrap: pretty;
}

.home-guest-intro {
  text-wrap: pretty;
}

.home-guest-signin {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}

.home-guest-signin-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: end;
  justify-items: start;
  gap: var(--space-3);
  width: 100%;
}

.home-guest-signin-field {
  justify-self: stretch;
}

@media (min-width: 32rem) {
  .home-guest-signin-row {
    grid-template-columns: repeat(2, minmax(0, 1fr)) auto;
  }
}

.home-guest-signin-keep {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.home-guest-signin-keep label {
  font-size: var(--font-size-small);
}

.home-guest-signin-error {
  margin: 0;
  color: var(--critical-text);
}

.home-guest-account-hint {
  margin: 0;
  font-size: var(--font-size-body);
  line-height: var(--line-height-body);
  color: var(--text-secondary);
}

.home-guest-steps {
  counter-reset: step;
  margin: 0;
  list-style: none;
}

.home-guest-step {
  counter-increment: step;
  display: grid;
  grid-template-columns: var(--space-8) minmax(0, 1fr);
  column-gap: var(--space-3);
  row-gap: var(--space-2);
  padding: var(--space-4);
  border-bottom: 1px solid var(--grid);
}

.home-guest-step:last-child {
  border-bottom: 0;
}

.home-guest-step::before {
  content: counter(step);
  grid-row: 1 / span 2;
  color: var(--muted);
  font-size: var(--font-size-body-strong);
  font-variant-numeric: tabular-nums;
  line-height: var(--line-height-body-strong);
}

.home-guest-step-title {
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-body-strong);
  color: var(--text-primary);
}

.home-guest-step-text {
  font-size: var(--font-size-body);
  line-height: var(--line-height-body);
  color: var(--text-secondary);
  text-wrap: pretty;
}
</style>
