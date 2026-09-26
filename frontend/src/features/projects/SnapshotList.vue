<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'

import SnapshotItem from './SnapshotItem.vue'
import { useSnapshotList } from './useSnapshots'

const props = defineProps<{ projectId: string }>()
const { t } = useI18n()
const query = useSnapshotList(toRef(props, 'projectId'))
const snapshots = computed(() => query.data.value?.pages.flatMap((page) => page.items) ?? [])
const accessUnavailable = computed(() => {
  const error = query.error.value
  return (
    error instanceof ApiError && error.status !== null && [401, 403, 404].includes(error.status)
  )
})
function loadMore(): void {
  if (!query.isFetching.value) void query.fetchNextPage()
}
</script>

<template>
  <div class="snapshot-list">
    <template v-if="query.isPending.value">
      <AppFeedback class="app-card" announcement="polite">{{ t('data.loading') }}</AppFeedback>
      <div class="snapshot-list-skeleton" aria-hidden="true">
        <div v-for="row in 3" :key="row" class="snapshot-skeleton app-resource-card">
          <span></span><span></span><span></span>
        </div>
      </div>
    </template>
    <AppFeedback
      v-else-if="accessUnavailable"
      class="app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('data.accessUnavailable') }}
      <template #actions>
        <AppButton :to="{ name: 'projects' }" variant="ghost">{{ t('projects.title') }}</AppButton>
      </template>
    </AppFeedback>
    <AppFeedback
      v-else-if="query.isError.value && !query.data.value"
      class="app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('data.loadError') }}
      <template #actions>
        <AppButton
          class="snapshot-list-retry"
          variant="ghost"
          :disabled="query.isFetching.value"
          @click="() => query.refetch()"
        >
          {{ t('projects.retry') }}
        </AppButton>
      </template>
    </AppFeedback>
    <template v-else>
      <div v-if="snapshots.length === 0" class="snapshot-list-empty app-card">
        <p>{{ t('data.empty') }}</p>
        <p>{{ t('data.emptyHint') }}</p>
      </div>
      <ul v-else class="snapshot-list-items" :aria-busy="query.isFetching.value || undefined">
        <SnapshotItem v-for="snapshot in snapshots" :key="snapshot.id" :snapshot="snapshot" />
      </ul>
      <AppFeedback
        v-if="query.isError.value"
        class="snapshot-list-feedback app-card"
        announcement="assertive"
        tone="critical"
      >
        {{ query.isFetchNextPageError.value ? t('data.loadMoreError') : t('data.loadError') }}
        <template v-if="!query.isFetchNextPageError.value" #actions>
          <AppButton
            class="snapshot-list-retry"
            variant="ghost"
            :disabled="query.isFetching.value"
            @click="() => query.refetch()"
            >{{ t('projects.retry') }}</AppButton
          >
        </template>
      </AppFeedback>
      <AppFeedback
        v-if="query.isFetchingNextPage.value"
        class="snapshot-list-feedback app-card"
        announcement="polite"
      >
        {{ t('data.loadingMore') }}
      </AppFeedback>
      <AppButton
        v-if="query.hasNextPage.value"
        class="snapshot-list-load-more"
        variant="ghost"
        :disabled="query.isFetching.value"
        @click="loadMore"
      >
        {{ query.isFetchNextPageError.value ? t('projects.retry') : t('data.loadMore') }}
      </AppButton>
    </template>
  </div>
</template>

<style scoped>
.snapshot-list {
  min-inline-size: 0;
}
.snapshot-list-empty {
  color: var(--text-secondary);
}
.snapshot-list-empty p {
  max-inline-size: 65ch;
  margin: 0 0 var(--space-2);
}
.snapshot-list-items,
.snapshot-list-skeleton {
  display: grid;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}
.snapshot-list-feedback,
.snapshot-list-load-more,
.snapshot-list-skeleton {
  margin-block-start: var(--space-4);
}
.snapshot-skeleton {
  display: grid;
  gap: var(--space-3);
}
.snapshot-skeleton span {
  block-size: 1em;
  inline-size: 35%;
  background: var(--border);
  border-radius: var(--radius-input);
}
.snapshot-skeleton span:first-child {
  inline-size: 65%;
  block-size: 1.5em;
}
</style>
