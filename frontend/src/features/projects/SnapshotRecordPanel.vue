<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import PersonRecordDetails from '@/features/review/PersonRecordDetails.vue'

import type { ImportedPerson } from './useSnapshotData'

withDefaults(
  defineProps<{
    selectedId: string
    title: string
    record: ImportedPerson | null
    isPending: boolean
    isError: boolean
    isFetching: boolean
    embedded?: boolean
  }>(),
  { embedded: false },
)

const emit = defineEmits<{
  retry: []
}>()
const { t } = useI18n()
</script>

<template>
  <section
    id="snapshot-record-detail-panel"
    class="snapshot-record-detail"
    :class="{
      'app-resource-card': !embedded,
      'snapshot-record-detail--embedded': embedded,
    }"
    aria-labelledby="snapshot-record-detail-title"
    tabindex="-1"
  >
    <div v-if="!embedded" class="snapshot-record-detail-heading">
      <div>
        <h3 id="snapshot-record-detail-title" tabindex="-1">{{ title }}</h3>
        <p class="snapshot-record-detail-id">{{ selectedId }}</p>
      </div>
    </div>
    <h3 v-else id="snapshot-record-detail-title" class="snapshot-record-visually-hidden">
      {{ title }}
    </h3>
    <AppFeedback v-if="isPending && !record" announcement="polite">
      {{ t('data.records.loadingRecord') }}
    </AppFeedback>
    <AppFeedback v-if="isError || (!isPending && !record)" announcement="assertive" tone="critical">
      {{ t('data.records.recordError') }}
      <template #actions>
        <AppButton
          class="snapshot-record-retry"
          variant="ghost"
          :disabled="isFetching"
          @click="emit('retry')"
        >
          {{ t('projects.retry') }}
        </AppButton>
      </template>
    </AppFeedback>
    <PersonRecordDetails v-if="record" :record="record" />
  </section>
</template>

<style scoped>
.snapshot-record-detail-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  margin-block-end: var(--space-4);
}

.snapshot-record-visually-hidden {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

.snapshot-record-detail h3 {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  overflow-wrap: anywhere;
}

.snapshot-record-detail-id {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}
</style>
