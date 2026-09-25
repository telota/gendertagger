<script setup lang="ts">
import { PhSignIn } from '@phosphor-icons/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'

const { t } = useI18n()

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
</script>

<template>
  <div class="home-guest">
    <p class="home-guest-lede">{{ t('home.guest.lede') }}</p>
    <p class="home-guest-intro">{{ t('home.guest.intro') }}</p>

    <div class="home-guest-action">
      <AppButton :to="{ name: 'login' }">
        <PhSignIn :size="18" aria-hidden="true" />
        {{ t('home.guest.signIn') }}
      </AppButton>
      <p class="home-guest-account-hint">{{ t('home.guest.accountHint') }}</p>
    </div>

    <ol class="home-guest-steps" :aria-label="t('home.guest.stepsLabel')">
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

.home-guest-lede {
  max-width: 60ch;
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-title);
  font-weight: var(--weight-regular);
  line-height: var(--line-height-title);
  color: var(--text-primary);
  text-wrap: pretty;
}

.home-guest-intro {
  max-width: 65ch;
  margin: 0 0 var(--space-6);
  font-size: var(--font-size-body-strong);
  line-height: var(--line-height-body);
  color: var(--text-secondary);
  text-wrap: pretty;
}

.home-guest-action {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  margin-bottom: var(--space-10);
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
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--grid);
}

.home-guest-step {
  counter-increment: step;
  display: grid;
  grid-template-columns: var(--space-8) minmax(0, 1fr);
  column-gap: var(--space-3);
  row-gap: var(--space-2);
  padding: var(--space-6) 0;
  border-bottom: 1px solid var(--grid);
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
  max-width: 60ch;
  font-size: var(--font-size-body);
  line-height: var(--line-height-body);
  color: var(--text-secondary);
}
</style>
