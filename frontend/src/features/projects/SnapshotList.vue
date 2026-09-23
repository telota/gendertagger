<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'

import SnapshotItem from './SnapshotItem.vue'
import { useSnapshotList } from './useSnapshots'

const props = defineProps<{ projectId: string }>()

const { t } = useI18n()

const query = useSnapshotList(toRef(props, 'projectId'))
const snapshots = computed(() => query.data.value?.pages.flatMap((page) => page.items) ?? [])

function loadMore(): void {
  void query.fetchNextPage()
}
</script>

<template>
  <section class="snapshot-list" aria-labelledby="snapshot-list-heading">
    <h2 id="snapshot-list-heading" class="snapshot-list-title">
      {{ t('projects.snapshots.title') }}
    </h2>

    <p v-if="query.isPending.value" role="status">{{ t('projects.loading') }}</p>
    <div v-else-if="query.isError.value" class="snapshot-list-error">
      <p role="alert">{{ t('projects.snapshots.loadError') }}</p>
      <AppButton class="snapshot-list-retry" type="button" @click="() => query.refetch()">
        {{ t('projects.retry') }}
      </AppButton>
    </div>
    <template v-else>
      <p v-if="snapshots.length === 0" class="snapshot-list-empty">
        {{ t('projects.snapshots.empty') }}
      </p>
      <ul v-else class="snapshot-list-items">
        <SnapshotItem v-for="snapshot in snapshots" :key="snapshot.id" :snapshot="snapshot" />
      </ul>
      <AppButton
        v-if="query.hasNextPage.value"
        class="snapshot-list-load-more"
        type="button"
        @click="loadMore"
      >
        {{ t('projects.loadMore') }}
      </AppButton>
    </template>
  </section>
</template>

<style scoped>
.snapshot-list {
  margin-top: var(--space-8);
}

.snapshot-list-title {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.snapshot-list-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.snapshot-list-error p {
  margin: 0;
  color: var(--critical);
}

.snapshot-list-empty {
  color: var(--text-secondary);
}

.snapshot-list-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin: 0 0 var(--space-4);
  padding: 0;
  list-style: none;
}
</style>
