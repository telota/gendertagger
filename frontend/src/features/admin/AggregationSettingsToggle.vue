<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { components } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import { useDraftRegistration } from '@/composables/useDraftNavigation'

import type { AdminSettings } from './useAdminSettings'

const props = defineProps<{
  settings: AdminSettings
  isSubmitting: boolean
}>()

const emit = defineEmits<{
  save: [command: components['schemas']['AggregationSettingsUpdate']]
}>()

const { t } = useI18n()
const allowPartial = ref(props.settings.allow_partial_reference_aggregation)
const hasChanges = computed(
  () => allowPartial.value !== props.settings.allow_partial_reference_aggregation,
)

useDraftRegistration(
  () => hasChanges.value,
  () => {
    allowPartial.value = props.settings.allow_partial_reference_aggregation
  },
)

function save(): void {
  if (!hasChanges.value || props.isSubmitting) return
  emit('save', {
    expected_revision: props.settings.revision,
    allow_partial_reference_aggregation: allowPartial.value,
  })
}
</script>

<template>
  <section class="aggregation-settings" aria-labelledby="aggregation-settings-heading">
    <div class="aggregation-settings-heading">
      <h2 id="aggregation-settings-heading">{{ t('adminSettings.aggregation.title') }}</h2>
      <p>{{ t('adminSettings.aggregation.description') }}</p>
    </div>
    <form class="aggregation-settings-card app-card" novalidate @submit.prevent="save">
      <div class="aggregation-settings-toggle">
        <input id="allow-partial-reference-aggregation" v-model="allowPartial" type="checkbox" />
        <label for="allow-partial-reference-aggregation">
          {{ t('adminSettings.aggregation.toggleLabel') }}
        </label>
      </div>
      <p class="aggregation-settings-hint">{{ t('adminSettings.aggregation.hint') }}</p>
      <AppButton
        class="aggregation-settings-submit"
        type="submit"
        :disabled="!hasChanges || isSubmitting"
      >
        {{ isSubmitting ? t('adminSettings.aggregation.saving') : t('adminSettings.aggregation.save') }}
      </AppButton>
    </form>
  </section>
</template>

<style scoped>
.aggregation-settings {
  margin-block-end: var(--space-8);
}

.aggregation-settings-heading {
  margin-block-end: var(--space-4);
}

.aggregation-settings-heading h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.aggregation-settings-heading p {
  max-inline-size: 65ch;
  margin: var(--space-2) 0 0;
  color: var(--text-secondary);
}

.aggregation-settings-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.aggregation-settings-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.aggregation-settings-hint {
  margin: 0;
  max-inline-size: 65ch;
  color: var(--text-secondary);
}
</style>
