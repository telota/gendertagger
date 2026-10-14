<script setup lang="ts">
// The "Anderen Datenstand wählen" card (D28): a short prompt plus the one way into the full,
// unlisted history page (ProjectSnapshotsView) — promoted out of ProjectCurrentSnapshot's own
// card into its own, so Übersicht reads as three cards: facts, the current dataset, and this.
import { PhArrowRight } from '@phosphor-icons/vue'
import { computed, toRef } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'

import ProjectOverviewSection from './ProjectOverviewSection.vue'
import { snapshotStats } from './projectStats'
import { useSnapshotList } from './useSnapshots'

const props = defineProps<{ projectId: string }>()
const { t, n } = useI18n()

const snapshots = useSnapshotList(toRef(props, 'projectId'))
const stats = computed(() => {
  const page = snapshots.data.value?.pages[0]
  return page ? snapshotStats(page.items, page.has_more) : null
})
// `loaded` always includes the current/newest snapshot shown on its own card; this counts the rest.
const otherCount = computed(() => (stats.value ? Math.max(stats.value.loaded - 1, 0) : null))
const otherCountLabel = computed(() => {
  if (otherCount.value === null) return null
  return stats.value?.hasMore
    ? t('projects.overview.atLeast', { count: n(otherCount.value, 'integer') })
    : n(otherCount.value, 'integer')
})
</script>

<template>
  <ProjectOverviewSection :title="t('projects.overview.other.title')">
    <p v-if="snapshots.isPending.value" role="status">{{ t('projects.loading') }}</p>
    <AppFeedback v-else-if="snapshots.isError.value" tone="critical" announcement="polite">
      <p>{{ t('projects.overview.data.loadError') }}</p>
      <template #actions>
        <AppButton type="button" variant="ghost" @click="() => snapshots.refetch()">{{
          t('projects.retry')
        }}</AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="otherCount !== null">
      <p v-if="otherCount === 0" class="other-snapshots-empty">
        {{ t('projects.overview.other.empty') }}
      </p>
      <p v-else class="other-snapshots-description">
        {{ t('projects.overview.other.description', { count: otherCountLabel }) }}
      </p>
    </template>
    <div class="other-snapshots-actions">
      <AppButton
        class="project-overview-other-link"
        :to="{ name: 'projectSnapshots', params: { projectId } }"
        variant="ghost"
      >
        {{ t('projects.overview.other.browse') }}
        <PhArrowRight :size="18" aria-hidden="true" />
      </AppButton>
    </div>
  </ProjectOverviewSection>
</template>

<style scoped>
.other-snapshots-empty,
.other-snapshots-description {
  margin: 0;
  color: var(--text-secondary);
}
.other-snapshots-actions {
  display: flex;
  justify-content: flex-end;
  margin-block-start: var(--space-4);
}
.other-snapshots-actions svg {
  flex-shrink: 0;
}
</style>
