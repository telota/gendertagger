<script setup lang="ts">
import { PhArrowRight } from '@phosphor-icons/vue'
import { computed, toRef } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useRunList } from '@/features/runs/useRuns'

import ProjectOverviewSection from './ProjectOverviewSection.vue'
import ProjectStat from './ProjectStat.vue'
import ProjectStatList from './ProjectStatList.vue'
import { snapshotStats } from './projectStats'
import { useSnapshotList } from './useSnapshots'

const props = defineProps<{ projectId: string }>()
const { t, d, n } = useI18n()

const snapshots = useSnapshotList(toRef(props, 'projectId'))
// Only the newest page: the figures are exact unless the server says there is more, and then they
// read as a lower bound ("50+") instead of pretending to be a total.
const stats = computed(() => {
  const page = snapshots.data.value?.pages[0]
  return page ? snapshotStats(page.items, page.has_more) : null
})
const latest = computed(() => stats.value?.latestReady ?? null)

const runs = useRunList(
  computed(() => latest.value?.id ?? ''),
  computed(() => latest.value !== null),
)
const runCount = computed(() => {
  const page = runs.data.value?.pages[0]
  return page ? { value: page.items.length, hasMore: page.has_more } : null
})

function count(value: number, hasMore: boolean): string {
  return hasMore
    ? t('projects.overview.atLeast', { count: n(value, 'integer') })
    : n(value, 'integer')
}
</script>

<template>
  <ProjectOverviewSection :title="t('projects.overview.data.title')">
    <p v-if="snapshots.isPending.value" role="status">{{ t('projects.loading') }}</p>
    <AppFeedback v-else-if="snapshots.isError.value" tone="critical" announcement="polite">
      <p>{{ t('projects.overview.data.loadError') }}</p>
      <template #actions>
        <AppButton type="button" variant="ghost" @click="() => snapshots.refetch()">{{
          t('projects.retry')
        }}</AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="stats">
      <p v-if="stats.loaded === 0" class="data-empty">{{ t('projects.overview.data.empty') }}</p>
      <ProjectStatList v-else>
        <ProjectStat>
          <template #label>{{ t('projects.overview.data.snapshots') }}</template>
          {{ count(stats.loaded, stats.hasMore) }}
        </ProjectStat>
        <template v-if="latest">
          <ProjectStat v-if="latest.record_count != null">
            <template #label>{{ t('projects.overview.data.records') }}</template>
            {{ n(latest.record_count, 'integer') }}
          </ProjectStat>
          <ProjectStat>
            <template #label>{{ t('projects.overview.data.imported') }}</template>
            {{ d(new Date(latest.ready_at ?? latest.created_at), 'date') }}
          </ProjectStat>
        </template>
        <ProjectStat v-if="runCount">
          <template #label>{{ t('projects.overview.data.runs') }}</template>
          {{ count(runCount.value, runCount.hasMore) }}
        </ProjectStat>
        <ProjectStat v-if="stats.inProgress > 0">
          <template #label>{{ t('projects.overview.data.inProgress') }}</template>
          {{ n(stats.inProgress, 'integer') }}
        </ProjectStat>
        <ProjectStat v-if="stats.failed > 0" tone="critical">
          <template #label>{{ t('projects.overview.data.failed') }}</template>
          {{ n(stats.failed, 'integer') }}
        </ProjectStat>
      </ProjectStatList>
    </template>
    <!-- Navigation never waits on the figures: the list stays reachable if they fail to load. -->
    <div class="data-actions">
      <AppButton
        :to="{ name: 'projectSnapshots', params: { projectId } }"
        variant="ghost"
        class="project-overview-data-link"
      >
        {{ t('data.viewImportedData') }}
        <PhArrowRight :size="18" aria-hidden="true" />
      </AppButton>
    </div>
  </ProjectOverviewSection>
</template>

<style scoped>
.data-empty {
  margin: 0;
  color: var(--text-secondary);
}
.data-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-block-start: var(--space-4);
}
.data-actions svg {
  flex-shrink: 0;
}
p[role='status'] {
  margin: 0;
}
</style>
