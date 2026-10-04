<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppSelectField from '@/components/base/AppSelectField.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useProjectIdentity } from '@/composables/useProjectIdentity'
import { useRequireSession } from '@/composables/useRequireSession'
import { projectKey } from '@/composables/resourceQueries'
import { useImportedSnapshot } from '@/composables/useSnapshotData'
import { hasProjectRole } from '@/composables/projectRoles'

import SnapshotAnnotationDetail from './SnapshotAnnotationDetail.vue'
import VocabBadge from '@/components/domain/VocabBadge.vue'
import { reviewItemName } from '@/components/domain/reviewItemName'
import { isRecoverableReviewError, retainedReviewData } from '@/composables/retainedReviewData'
import { CANONICAL_LABELS, WORKFLOW_STATES, useVocabularyGloss } from '@/composables/useVocabulary'
import {
  useSnapshotAnnotationItem,
  useSnapshotAnnotationItems,
  type SnapshotAnnotationFilters,
} from './useSnapshotAnnotations'
import type { components } from '@/api/schema'

type CanonicalLabel = components['schemas']['CanonicalLabel']
type ReviewWorkflowState = components['schemas']['ReviewWorkflowState']

const { t, d } = useI18n()
const route = useRoute()
const router = useRouter()
const { session, isSignedIn, retrySession } = useRequireSession()
const { projectId, query: projectQuery } = useProjectIdentity()
const cache = useQueryClient()
const project = computed(() => {
  const value = retainedReviewData(
    cache,
    projectKey(projectId.value, session.user?.id),
    session.canUsePrivateNavigation,
    projectQuery.status.value,
    projectQuery.data.value,
    projectQuery.error.value,
  )
  return value?.id === projectId.value && hasProjectRole(value.current_user_role, 'viewer')
    ? value
    : null
})
const snapshotId = computed(() => String(route.params.snapshotId ?? ''))
const teiId = computed(() => String(route.params.teiId ?? ''))
const snapshotQuery = useImportedSnapshot(
  projectId,
  snapshotId,
  computed(() => project.value !== null),
)
const snapshot = computed(() => {
  const value = snapshotQuery.data.value
  return (!snapshotQuery.isError.value || isRecoverableReviewError(snapshotQuery.error.value)) &&
    value?.id === snapshotId.value &&
    value.project_id === projectId.value &&
    value.status === 'ready'
    ? value
    : null
})
const enabled = computed(() => project.value !== null && snapshot.value !== null)
const canReview = computed(
  () => project.value !== null && hasProjectRole(project.value.current_user_role, 'reviewer'),
)
const gloss = useVocabularyGloss()
const filters = computed<SnapshotAnnotationFilters>(() => ({
  q: typeof route.query.q === 'string' ? route.query.q : '',
  workflowState: WORKFLOW_STATES.find((value) => value === route.query.state) ?? null,
  humanLabel: CANONICAL_LABELS.find((value) => value === route.query.label) ?? null,
}))
const search = ref('')
const state = ref<ReviewWorkflowState | ''>('')
const label = ref<CanonicalLabel | ''>('')
watch(
  filters,
  (value) => {
    search.value = value.q
    state.value = value.workflowState ?? ''
    label.value = value.humanLabel ?? ''
  },
  { immediate: true },
)
const list = useSnapshotAnnotationItems(snapshotId, filters, enabled)
const people = computed(
  () =>
    list.data.value?.pages
      .flatMap((page) => page.items)
      .filter((item) => item.snapshot_id === snapshotId.value) ?? [],
)
const announce = computed(() =>
  list.isSuccess.value ? t('review.list.count', { count: people.value.length }) : '',
)
const selected = useSnapshotAnnotationItem(snapshotId, teiId, enabled)
const person = computed(() =>
  (!selected.isError.value || isRecoverableReviewError(selected.error.value)) &&
  selected.data.value?.snapshot_id === snapshotId.value &&
  selected.data.value.tei_id === teiId.value
    ? selected.data.value
    : null,
)
const contextFresh = computed(
  () =>
    projectQuery.isSuccess.value &&
    !projectQuery.isFetching.value &&
    snapshotQuery.isSuccess.value &&
    !snapshotQuery.isFetching.value,
)
const decisionContextReady = computed(
  () => contextFresh.value && selected.isSuccess.value && !selected.isFetching.value,
)
function applyFilters(): void {
  void router.push({
    query: {
      ...(search.value.trim() ? { q: search.value.trim() } : {}),
      ...(state.value ? { state: state.value } : {}),
      ...(label.value ? { label: label.value } : {}),
    },
  })
}
function retryContext(): void {
  void projectQuery.refetch()
  void snapshotQuery.refetch()
}
</script>

<template>
  <main class="snapshot-annotations app-page-frame app-page-frame--dense">
    <header class="annotation-heading app-page-heading">
      <h1 class="app-page-heading__title">
        {{ canReview ? t('review.people.title') : t('annotation.browseTitle') }}
      </h1>
      <div class="app-page-heading__actions">
        <AppButton
          variant="ghost"
          :to="{
            name: canReview ? 'projectAnnotation' : 'projectSnapshots',
            params: { projectId },
          }"
          >{{ t('taskEntry.changeSelection') }}</AppButton
        >
      </div>
    </header>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      announcement="polite"
      >{{ t('review.loading') }}</AppFeedback
    >
    <AppFeedback v-else-if="session.status === 'error'" announcement="assertive" tone="critical"
      >{{ t('projects.sessionLoadError')
      }}<template #actions
        ><AppButton variant="ghost" @click="retrySession">{{
          t('review.retry')
        }}</AppButton></template
      ></AppFeedback
    >
    <template v-else-if="isSignedIn">
      <AppFeedback
        v-if="projectQuery.isPending.value || (project && snapshotQuery.isPending.value)"
        announcement="polite"
        >{{ t('review.loading') }}</AppFeedback
      >
      <AppFeedback v-else-if="!enabled" announcement="assertive" tone="critical"
        >{{ t('taskEntry.selectionUnavailable')
        }}<template #actions
          ><AppButton variant="ghost" @click="retryContext">{{
            t('review.retry')
          }}</AppButton></template
        ></AppFeedback
      >
      <template v-else-if="snapshot">
        <AppFeedback
          v-if="projectQuery.isError.value || snapshotQuery.isError.value"
          tone="critical"
          announcement="assertive"
        >
          {{ t('review.refreshError') }}
          <template #actions
            ><AppButton variant="ghost" @click="retryContext">{{
              t('review.retry')
            }}</AppButton></template
          >
        </AppFeedback>
        <div class="annotation-context">
          <div>
            <p>
              {{ t('data.snapshotTitle', { date: d(new Date(snapshot.created_at), 'timestamp') }) }}
            </p>
            <p>{{ t('annotation.hint') }}</p>
          </div>
          <AppButton
            v-if="canReview"
            variant="text"
            :to="{
              name: 'projectAnnotation',
              params: { projectId },
              query: { snapshot: snapshot.id, evidence: '1' },
            }"
            >{{ t('annotation.evidence') }}</AppButton
          >
        </div>
        <form class="annotation-filters" @submit.prevent="applyFilters">
          <AppTextField
            id="annotation-search"
            v-model="search"
            type="search"
            :label="t('annotation.search')"
          />
          <AppSelectField id="annotation-state" v-model="state" :label="t('review.detail.state')">
            <option value="">{{ t('annotation.allStates') }}</option>
            <option v-for="value in WORKFLOW_STATES" :key="value" :value="value">
              {{ gloss.workflow(value) }}
            </option>
          </AppSelectField>
          <AppSelectField id="annotation-label" v-model="label" :label="t('annotation.humanLabel')">
            <option value="">{{ t('annotation.allLabels') }}</option>
            <option v-for="value in CANONICAL_LABELS" :key="value" :value="value">
              {{ value }}
            </option>
          </AppSelectField>
          <AppButton variant="ghost" type="submit">{{ t('annotation.searchSubmit') }}</AppButton>
        </form>
        <p class="annotation-announce" role="status">{{ announce }}</p>
        <div class="annotation-workbench">
          <section class="annotation-register" aria-labelledby="annotation-list-heading">
            <h2 id="annotation-list-heading" class="annotation-column-title">
              {{ t('review.list.title') }}
            </h2>
            <AppFeedback v-if="list.isPending.value" announcement="polite">{{
              t('review.loading')
            }}</AppFeedback>
            <AppFeedback v-if="list.isError.value" announcement="assertive" tone="critical"
              >{{ t('annotation.loadError')
              }}<template #actions
                ><AppButton variant="ghost" @click="list.refetch()">{{
                  t('review.retry')
                }}</AppButton></template
              ></AppFeedback
            >
            <p v-else-if="list.isSuccess.value && !people.length" role="status">
              {{ t('annotation.empty') }}
            </p>
            <ul class="annotation-people" :aria-label="t('review.list.label')">
              <li v-for="entry in people" :key="entry.tei_id">
                <RouterLink
                  class="annotation-row"
                  :to="{
                    name: 'snapshotAnnotations',
                    params: { projectId, snapshotId, teiId: entry.tei_id },
                    query: route.query,
                  }"
                  :aria-current="teiId === entry.tei_id ? 'true' : undefined"
                  :aria-label="
                    canReview
                      ? t('annotation.openNamed', { name: reviewItemName(entry) })
                      : t('annotation.openReadOnly', { name: reviewItemName(entry) })
                  "
                >
                  <span class="annotation-row-main">
                    <span class="annotation-row-name">{{ reviewItemName(entry) }}</span>
                    <code>{{ entry.tei_id }}</code>
                  </span>
                  <span class="annotation-row-badges">
                    <VocabBadge v-if="entry.human_label" :value="entry.human_label" kind="label" />
                    <span class="annotation-row-state">{{ entry.workflow_state }}</span>
                  </span>
                </RouterLink>
              </li>
            </ul>
            <AppButton
              v-if="list.hasNextPage.value"
              variant="ghost"
              :disabled="list.isFetchingNextPage.value"
              @click="list.fetchNextPage()"
              >{{ t('annotation.more') }}</AppButton
            >
          </section>
          <section class="annotation-person" aria-labelledby="annotation-detail-heading">
            <h2 id="annotation-detail-heading" class="annotation-visually-hidden">
              {{ t('review.detail.title') }}
            </h2>
            <p v-if="!teiId" class="annotation-muted">{{ t('annotation.selectPerson') }}</p>
            <AppFeedback v-else-if="selected.isPending.value" announcement="polite">{{
              t('review.loading')
            }}</AppFeedback>
            <AppFeedback v-else-if="!person" announcement="assertive" tone="critical"
              >{{ t('annotation.personError')
              }}<template #actions
                ><AppButton variant="ghost" @click="selected.refetch()">{{
                  t('review.retry')
                }}</AppButton></template
              ></AppFeedback
            >
            <template v-else>
              <AppFeedback v-if="selected.isError.value" tone="critical" announcement="assertive">
                {{ t('review.refreshError') }}
                <template #actions>
                  <AppButton variant="ghost" @click="selected.refetch()">
                    {{ t('review.retry') }}
                  </AppButton>
                </template>
              </AppFeedback>
              <SnapshotAnnotationDetail
                :key="`${session.user?.id}:${snapshotId}:${person.tei_id}`"
                :item="person"
                :can-review="canReview"
                :context-ready="decisionContextReady"
              />
            </template>
          </section>
        </div>
      </template>
    </template>
  </main>
</template>

<style scoped>
.snapshot-annotations {
  container: annotations / inline-size;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-4);
  overflow-wrap: anywhere;
}

.annotation-context {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
}

.annotation-heading {
  margin-block-end: 0;
}

.annotation-context {
  padding-block: var(--space-3);
  border-block: 1px solid var(--grid);
}

.annotation-context > div {
  min-width: 0;
}

.annotation-context p {
  max-inline-size: 70ch;
  margin: 0;
}

.annotation-context p:first-child {
  font-weight: var(--weight-semibold);
}

.annotation-context p + p {
  margin-block-start: var(--space-1);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.annotation-filters,
.annotation-register,
.annotation-person {
  min-width: 0;
  padding: var(--page-gutter);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.annotation-filters {
  --field-label-size: inherit;
  --field-label-color: var(--text-primary);
  --field-control-width: 100%;
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: var(--space-3);
}

.annotation-filters > div {
  display: grid;
  min-width: 0;
  flex: 1 1 12rem;
  gap: var(--space-2);
}

.annotation-filters :deep(input),
.annotation-filters :deep(select) {
  padding: var(--space-2);
}

.annotation-announce,
.annotation-muted {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.annotation-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  gap: var(--space-4);
}

@container annotations (min-width: 42rem) {
  .annotation-workbench {
    grid-template-columns: minmax(18rem, 1fr) minmax(22rem, 2fr);
  }
}

.annotation-column-title {
  margin: 0 0 var(--space-3);
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.annotation-people {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0 0 var(--space-3);
  padding: 0;
  list-style: none;
}

.annotation-row {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid transparent;
  border-radius: var(--radius-card);
  color: var(--text-primary);
  text-align: start;
  text-decoration: none;
}

.annotation-row:hover {
  background: var(--surface-1);
}

.annotation-row[aria-current='true'] {
  border-color: var(--accent);
  background: var(--surface-1);
}

.annotation-row-main {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.annotation-row-name {
  font-weight: var(--weight-semibold);
}

.annotation-row code,
.annotation-row-state {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.annotation-row code {
  overflow-wrap: anywhere;
}

.annotation-row-badges {
  display: flex;
  flex: none;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-1);
}

.annotation-visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
