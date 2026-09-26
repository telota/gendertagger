<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, toRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import { reviewItemName } from '@/features/review/reviewItemName'
import { useSessionStore } from '@/stores/session'

import SnapshotRecordPanel from './SnapshotRecordPanel.vue'
import { useImportedPeople, useImportedPerson } from './useSnapshotData'

const props = defineProps<{ projectId: string; snapshotId: string; recordCount: number | null }>()
const { t, n } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const enabled = computed(() => session.canUsePrivateNavigation)
const selectedId = computed(() =>
  typeof route.query.person === 'string' && route.query.person !== '' ? route.query.person : null,
)
const people = useImportedPeople(toRef(props, 'projectId'), toRef(props, 'snapshotId'), enabled)
const records = computed(
  () =>
    people.data.value?.pages
      .flatMap((page) => page.items)
      .filter((entry) => entry.dataset_snapshot_id === props.snapshotId) ?? [],
)
const person = useImportedPerson(
  toRef(props, 'projectId'),
  toRef(props, 'snapshotId'),
  selectedId,
  enabled,
)
const record = computed(() => {
  const value = person.data.value
  return value?.dataset_snapshot_id === props.snapshotId && value.tei_id === selectedId.value
    ? value
    : null
})
const selectedListRecord = computed(
  () => records.value.find((entry) => entry.tei_id === selectedId.value) ?? null,
)
const selectionPlacement = ref<{ id: string; external: boolean } | null>(null)
const hasExternalSelection = computed(
  () =>
    selectionPlacement.value?.id === selectedId.value && selectionPlacement.value.external === true,
)
const selectedTitle = computed(() => {
  const value = record.value ?? selectedListRecord.value
  return value ? reviewItemName(value) : t('data.records.detailTitle')
})

const listHeading = ref<HTMLElement | null>(null)
const recordsSection = ref<HTMLElement | null>(null)
const recordList = ref<HTMLElement | null>(null)
const recordPagination = ref<HTMLElement | null>(null)
let focusAfterClose: string | null = null
let layoutObserver: ResizeObserver | undefined

// Decide once per selection whether its detail belongs to the loaded table. Later cursor pages must not
// destroy and recreate an already-open deep-link panel if they happen to reveal the same TEI ID.
watch(
  [selectedId, () => people.isPending.value],
  ([id, isPending]) => {
    if (id === null) {
      selectionPlacement.value = null
      return
    }
    if (selectionPlacement.value?.id === id) return
    selectionPlacement.value = isPending
      ? null
      : { id, external: !records.value.some((entry) => entry.tei_id === id) }
  },
  { immediate: true },
)

function focusDetailPanel(): void {
  document.getElementById('snapshot-record-detail-panel')?.focus()
}

onMounted(() => {
  layoutObserver = new ResizeObserver(() => {
    const list = recordList.value
    const pagination = recordPagination.value
    const active = document.activeElement
    if (!(active instanceof HTMLElement)) return
    const activeRegion = list?.contains(active)
      ? list
      : pagination?.contains(active)
        ? pagination
        : null
    if (!activeRegion) return
    const row = active.closest<HTMLElement>('.snapshot-record-row')
    if (
      getComputedStyle(activeRegion).display === 'none' ||
      (row !== null && getComputedStyle(row).display === 'none')
    ) {
      focusDetailPanel()
    }
  })
  if (recordsSection.value) layoutObserver.observe(recordsSection.value)
})
onBeforeUnmount(() => layoutObserver?.disconnect())

function selectionLocation(teiId: string) {
  return {
    name: 'snapshotDetail',
    params: { projectId: props.projectId, snapshotId: props.snapshotId },
    query: { ...route.query, person: teiId },
  }
}

function recordToggleId(teiId: string): string {
  return `snapshot-record-view-${teiId}`
}

function isSelected(teiId: string): boolean {
  return selectedId.value === teiId
}

function toggleRecord(teiId: string): void {
  if (isSelected(teiId)) {
    closeRecord(teiId)
    return
  }
  focusAfterClose = null
  void router.push(selectionLocation(teiId))
}

function closeRecord(returnToId: string | null = selectedId.value): void {
  focusAfterClose = returnToId
  const query = { ...route.query }
  delete query.person
  void router.push({
    name: 'snapshotDetail',
    params: { projectId: props.projectId, snapshotId: props.snapshotId },
    query,
  })
}

watch(selectedId, async (id) => {
  const snapshot = props.snapshotId
  await nextTick()
  if (selectedId.value !== id || props.snapshotId !== snapshot || !enabled.value) return
  if (id !== null) {
    focusDetailPanel()
    return
  }
  const toggle = focusAfterClose ? document.getElementById(recordToggleId(focusAfterClose)) : null
  focusAfterClose = null
  ;(toggle ?? listHeading.value)?.focus()
})
</script>

<template>
  <section
    ref="recordsSection"
    class="snapshot-records"
    :class="{
      'snapshot-records--selected': selectedId !== null,
      'snapshot-records--external-selection': hasExternalSelection,
    }"
    aria-labelledby="snapshot-records-title"
  >
    <h2 id="snapshot-records-title" ref="listHeading" tabindex="-1">
      {{
        recordCount !== null
          ? t('data.records.titleWithCount', { count: n(recordCount, 'integer') })
          : t('data.records.title')
      }}
    </h2>
    <p class="snapshot-records-note">{{ t('data.records.description') }}</p>

    <div v-if="hasExternalSelection" class="snapshot-record-context">
      <p>{{ t('data.records.openedDirectly') }}</p>
      <AppButton
        class="snapshot-record-view snapshot-record-external-toggle"
        type="button"
        variant="ghost"
        :aria-expanded="true"
        aria-controls="snapshot-record-detail-panel"
        @click="closeRecord()"
      >
        {{ t('data.records.hideDetails') }}
      </AppButton>
    </div>
    <SnapshotRecordPanel
      v-if="selectedId && hasExternalSelection"
      :selected-id="selectedId"
      :title="selectedTitle"
      :record="record"
      :is-pending="person.isPending.value"
      :is-error="person.isError.value"
      :is-fetching="person.isFetching.value"
      class="snapshot-record-standalone"
      @retry="person.refetch()"
    />

    <AppFeedback
      v-if="people.isPending.value && records.length === 0"
      class="snapshot-record-list-status app-card"
      announcement="polite"
    >
      {{ t('data.records.loading') }}
    </AppFeedback>

    <div v-if="records.length" ref="recordList" class="snapshot-record-table-region">
      <AppScrollRegion
        class="snapshot-record-table-scroll app-card app-card--sectioned"
        :label="t('layout.tableRegion', { label: t('data.records.title') })"
      >
        <table class="snapshot-record-table">
          <thead>
            <tr>
              <th scope="col">{{ t('data.records.name') }}</th>
              <th scope="col">{{ t('data.records.teiId') }}</th>
              <th scope="col" class="snapshot-record-gnd-heading">
                {{ t('data.records.gnd') }}
              </th>
              <th scope="col" class="snapshot-record-actions-heading">
                {{ t('data.records.actions') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="entry in records" :key="entry.tei_id">
              <tr
                class="snapshot-record-row"
                :class="{ 'snapshot-record-row--selected': isSelected(entry.tei_id) }"
              >
                <th scope="row" class="snapshot-record-name">{{ reviewItemName(entry) }}</th>
                <td>
                  <code class="snapshot-record-id">{{ entry.tei_id }}</code>
                </td>
                <td class="snapshot-record-gnd">
                  <span
                    v-if="entry.gnd_id"
                    class="snapshot-record-gnd-badge"
                    :aria-label="t('data.records.gndReference', { id: entry.gnd_id })"
                    :title="t('data.records.gndReference', { id: entry.gnd_id })"
                  >
                    {{ t('data.records.gnd') }}
                  </span>
                  <span
                    v-else
                    class="snapshot-record-gnd-missing"
                    :aria-label="t('data.records.noGnd')"
                  >
                    {{ t('data.records.noGndSymbol') }}
                  </span>
                </td>
                <td class="snapshot-record-action">
                  <AppButton
                    :id="recordToggleId(entry.tei_id)"
                    class="snapshot-record-view"
                    type="button"
                    variant="ghost"
                    :aria-expanded="isSelected(entry.tei_id)"
                    :aria-controls="
                      isSelected(entry.tei_id) ? 'snapshot-record-detail-panel' : undefined
                    "
                    @click="toggleRecord(entry.tei_id)"
                  >
                    {{
                      isSelected(entry.tei_id)
                        ? t('data.records.hideDetails')
                        : t('data.records.showDetails')
                    }}
                  </AppButton>
                </td>
              </tr>
              <tr
                v-if="isSelected(entry.tei_id) && !hasExternalSelection"
                class="snapshot-record-detail-row"
              >
                <td colspan="4">
                  <div class="snapshot-record-detail-frame">
                    <SnapshotRecordPanel
                      :selected-id="entry.tei_id"
                      :title="selectedTitle"
                      :record="record"
                      :is-pending="person.isPending.value"
                      :is-error="person.isError.value"
                      :is-fetching="person.isFetching.value"
                      embedded
                      @retry="person.refetch()"
                    />
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </AppScrollRegion>
    </div>

    <AppFeedback
      v-else-if="!people.isPending.value && !people.isError.value"
      class="snapshot-records-empty app-card"
    >
      {{ t('data.records.empty') }}
    </AppFeedback>

    <div ref="recordPagination" class="snapshot-record-pagination">
      <AppFeedback
        v-if="people.isError.value"
        announcement="assertive"
        tone="critical"
        class="snapshot-record-feedback"
        :class="{ 'app-card': records.length === 0 }"
      >
        {{
          people.isFetchNextPageError.value
            ? t('data.records.loadMoreError')
            : t('data.records.loadError')
        }}
        <template #actions>
          <AppButton
            class="snapshot-records-retry"
            variant="ghost"
            :disabled="people.isFetching.value"
            @click="people.isFetchNextPageError.value ? people.fetchNextPage() : people.refetch()"
          >
            {{ t('projects.retry') }}
          </AppButton>
        </template>
      </AppFeedback>
      <AppFeedback
        v-if="people.isFetchingNextPage.value"
        announcement="polite"
        class="snapshot-record-feedback"
      >
        {{ t('data.records.loading') }}
      </AppFeedback>
      <AppButton
        v-if="people.hasNextPage.value && !people.isFetchNextPageError.value"
        class="snapshot-records-more"
        variant="ghost"
        :disabled="people.isFetching.value"
        @click="people.fetchNextPage()"
      >
        {{ t('data.records.loadMore') }}
      </AppButton>
    </div>
  </section>
</template>

<style scoped>
.snapshot-records {
  container: imported-records / inline-size;
  min-inline-size: 0;
}

.snapshot-records h2 {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  overflow-wrap: anywhere;
}

.snapshot-records-note {
  max-inline-size: 65ch;
  margin: var(--space-2) 0 var(--space-4);
  color: var(--text-secondary);
}

.snapshot-record-context {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2) var(--space-4);
  margin-block-end: var(--space-2);
}

.snapshot-record-context p {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-weight: var(--weight-semibold);
}

.snapshot-record-standalone {
  margin-block-end: var(--space-4);
}

.snapshot-record-table-region {
  min-inline-size: 0;
}

.snapshot-record-table-scroll {
  container: imported-record-table / inline-size;
}

.snapshot-record-table {
  inline-size: 100%;
  min-inline-size: 38rem;
  border-collapse: collapse;
  font-size: var(--font-size-body);
}

.snapshot-record-table th,
.snapshot-record-table td {
  padding: var(--space-3);
  border-block-end: 1px solid var(--grid);
  text-align: start;
  vertical-align: top;
}

.snapshot-record-table thead th {
  color: var(--text-secondary);
  font-size: var(--font-size-caption);
  font-weight: var(--weight-semibold);
  white-space: nowrap;
}

.snapshot-record-table tbody tr:last-child th,
.snapshot-record-table tbody tr:last-child td {
  border-block-end: 0;
}

.snapshot-record-name {
  font-weight: var(--weight-semibold);
  overflow-wrap: anywhere;
}

.snapshot-record-id {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}

.snapshot-record-table .snapshot-record-gnd-heading,
.snapshot-record-table .snapshot-record-gnd {
  inline-size: 1%;
  text-align: center;
}

.snapshot-record-gnd-badge {
  display: inline-flex;
  min-block-size: 1.5rem;
  align-items: center;
  padding-inline: var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  background: var(--surface-1);
  font-size: var(--font-size-caption);
  font-weight: var(--weight-semibold);
  letter-spacing: 0.03em;
}

.snapshot-record-gnd-missing {
  color: var(--muted);
}

.snapshot-record-table .snapshot-record-actions-heading,
.snapshot-record-table .snapshot-record-action {
  text-align: end;
}

.snapshot-record-action {
  inline-size: 1%;
}

.snapshot-record-view {
  max-inline-size: none;
  overflow-wrap: normal;
  white-space: nowrap;
}

.snapshot-record-table .snapshot-record-row--selected > *,
.snapshot-record-table .snapshot-record-detail-row > td {
  background: var(--surface-1);
}

.snapshot-record-table .snapshot-record-row--selected > * {
  border-block-end-color: transparent;
}

.snapshot-record-table .snapshot-record-detail-row > td {
  padding: 0;
}

.snapshot-record-detail-frame {
  position: sticky;
  inset-inline-start: 0;
  box-sizing: border-box;
  inline-size: min(100%, 100cqw);
}

.snapshot-record-feedback,
.snapshot-records-more,
.snapshot-record-list-status,
.snapshot-records-empty {
  margin-block-start: var(--space-4);
}

.snapshot-records-empty {
  color: var(--text-secondary);
}

@container imported-records (width < 44rem) {
  .snapshot-records--selected .snapshot-record-pagination,
  .snapshot-records--selected .snapshot-record-list-status {
    display: none;
  }

  .snapshot-records--external-selection .snapshot-record-table-region {
    display: none;
  }

  .snapshot-records--selected:not(.snapshot-records--external-selection) .snapshot-record-table {
    min-inline-size: 0;
  }

  .snapshot-records--selected:not(.snapshot-records--external-selection)
    .snapshot-record-table
    thead,
  .snapshot-records--selected:not(.snapshot-records--external-selection)
    .snapshot-record-row:not(.snapshot-record-row--selected) {
    display: none;
  }
}
</style>
