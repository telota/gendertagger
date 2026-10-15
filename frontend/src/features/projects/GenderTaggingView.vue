<script setup lang="ts">
// The guided presentation's one project page (D27): import, generate (preselecting every
// method), prüfen, and export — replacing projectOverview/projectImport/projectClassification and
// the per-dataset Redigieren entry with a single sequential flow. Advanced-presentation routes and
// components are unchanged; this view only adds a second, reduced path to the same capabilities.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppSelectField from '@/components/base/AppSelectField.vue'
import { hasProjectRole } from '@/composables/projectRoles'
import {
  AGGREGATABLE_EXECUTION_STATUSES,
  useAggregation,
  useCreateAggregation,
} from '@/composables/useAggregations'
import { useMethodList } from '@/composables/useMethods'
import { useProject, useSetWorkingAggregation } from '@/composables/useProjects'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { TERMINAL_RUN_STATUSES, useRun, useRunExecutions } from '@/composables/useRunDetail'
import { useCreateRun, useRunList } from '@/composables/useRuns'

import { useCreateExport, type ExportFormat } from '@/features/export/useExports'
import { useRunProgress } from '@/features/runs/useRunProgress'
import ProjectOverviewSection from './ProjectOverviewSection.vue'
import { useRoleLabel } from './useRoleLabel'
import { useSnapshotList } from './useSnapshots'
import { snapshotStats } from './projectStats'
import SnapshotImportForm from './SnapshotImportForm.vue'

const { t, n } = useI18n()
const router = useRouter()
const roleLabel = useRoleLabel()
const { session, isSignedIn, retrySession } = useRequireSession()
const projectId = useRouteParam('projectId')

const project = useProject(projectId, isSignedIn)
const canImport = computed(() => hasProjectRole(project.data.value?.current_user_role, 'operator'))
const canGenerate = canImport

const importOpen = ref(false)
const importMounted = ref(false)
// Guided mode hides the embedded form's own "weiteres Register importieren" (it would just
// duplicate this toggle, and leads nowhere useful once already imported): reopening the panel
// remounts a fresh form instead, so this toggle is the only way back to a blank upload.
const importInstance = ref(0)
function toggleImport(): void {
  importOpen.value = !importOpen.value
  if (importOpen.value) {
    importMounted.value = true
    importInstance.value += 1
  }
}
watch([() => session.user?.id, projectId], () => {
  importOpen.value = false
  importMounted.value = false
})

const snapshots = useSnapshotList(projectId, isSignedIn)
const latestReady = computed(() => {
  const page = snapshots.data.value?.pages[0]
  return page ? snapshotStats(page.items, page.has_more).latestReady : null
})
const teiPossible = computed(() => {
  const config = latestReady.value?.import_config
  if (!config) return true
  const sourceFormat = config['source_format']
  const packaging = config['packaging']
  return sourceFormat === 'tei' && (packaging === 'single' || packaging === 'loose')
})

// The project's working aggregation (ADR-0035) is the single source of truth for "done": it
// survives a reload, unlike any locally tracked run. The guided generate step below sets it
// itself the moment the aggregation it created completes (ADR-0035 does not do this automatically).
const workingAggregationId = computed(() => project.data.value?.working_aggregation_execution_id ?? null)
const workingAggregationEnabled = computed(() => workingAggregationId.value !== null)
const workingAggregation = useAggregation(
  computed(() => workingAggregationId.value ?? ''),
  workingAggregationEnabled,
)
// A working aggregation can outlive the dataset it was built from: once a newer snapshot finishes
// importing, that aggregation reflects the *previous* dataset, not the one Schritt 1 now shows as
// current. `isDone` must go back to false in that case, resetting Schritt 2's hint/button and
// re-locking Prüfen/Export, exactly as if nothing had been generated for the current dataset yet.
const workingRunId = computed(() => workingAggregation.data.value?.run_id ?? null)
const workingRun = useRun(
  computed(() => workingRunId.value ?? ''),
  computed(() => workingRunId.value !== null),
)
const workingDatasetStale = computed(
  () =>
    workingRun.data.value !== undefined &&
    latestReady.value !== null &&
    workingRun.data.value.dataset_snapshot_id !== latestReady.value.id,
)
const isDone = computed(
  () =>
    workingAggregationEnabled.value &&
    workingAggregation.data.value?.status === 'completed' &&
    !workingDatasetStale.value,
)

// Tracked only locally while this page stays mounted; a reload (or this component's own real-stack
// restart, mid-generation, found the hard way) would otherwise lose track of a run that goes on to
// finish successfully in the background — the button would just offer to start again over a dataset
// that in fact already has results, with nothing to show for the run that actually worked. The
// one-shot resume below re-adopts whatever run the server still remembers as this snapshot's most
// recent before any explicit generate can run, so Schritt 2 catches up instead of orphaning it.
const activeRunId = ref<string | null>(null)
const activeRunEnabled = computed(() => activeRunId.value !== null)
const activeRun = useRun(
  computed(() => activeRunId.value ?? ''),
  activeRunEnabled,
)
const activeExecutions = useRunExecutions(
  computed(() => activeRunId.value ?? ''),
  activeRunEnabled,
)
useRunProgress(
  computed(() => activeRunId.value ?? ''),
  activeRunEnabled,
)

const runListEnabled = computed(
  () => canGenerate.value && latestReady.value !== null && !isDone.value,
)
const runList = useRunList(
  computed(() => latestReady.value?.id ?? ''),
  runListEnabled,
)
// Settled, not just loaded: `isDone` only means something once the working aggregation (and the run
// behind it) has either resolved or definitively failed to — otherwise a run already turned into the
// working aggregation could read as "not done yet" purely because that other query hasn't come back,
// and get re-adopted into a duplicate aggregation.
const resumeReady = computed(
  () =>
    runList.data.value !== undefined &&
    project.isSuccess.value &&
    (!workingAggregationEnabled.value ||
      workingAggregation.isSuccess.value ||
      workingAggregation.isError.value) &&
    (workingRunId.value === null || workingRun.isSuccess.value || workingRun.isError.value),
)
let resumeChecked = false
watch(
  resumeReady,
  (ready) => {
    if (!ready || resumeChecked) return
    resumeChecked = true
    const mostRecentRun = runList.data.value?.pages[0]?.items[0] ?? null
    if (mostRecentRun !== null && activeRunId.value === null && !isDone.value) {
      activeRunId.value = mostRecentRun.id
    }
  },
  { immediate: true },
)

const methods = useMethodList(canGenerate)
const createRun = useCreateRun()
const createAggregation = useCreateAggregation()
const setWorking = useSetWorkingAggregation(projectId)

const runSucceeded = computed(
  () =>
    activeRun.data.value?.status === 'completed' ||
    activeRun.data.value?.status === 'completed_with_errors',
)
const runEnded = computed(() => {
  const status = activeRun.data.value?.status
  return status !== undefined && TERMINAL_RUN_STATUSES.has(status)
})
const runFailed = computed(() => runEnded.value && !runSucceeded.value)
const aggregatable = computed(() =>
  (activeExecutions.data.value ?? []).filter((execution) =>
    AGGREGATABLE_EXECUTION_STATUSES.has(execution.status),
  ),
)
const createdAggregationId = ref<string | null>(null)
const createdAggregationEnabled = computed(() => createdAggregationId.value !== null)
const createdAggregation = useAggregation(
  computed(() => createdAggregationId.value ?? ''),
  createdAggregationEnabled,
)
const aggregationFailed = computed(() => createAggregation.isError.value)
const aggregationDone = computed(() => createdAggregation.data.value?.status === 'completed')

let autoCreateAttempted = false
watch(
  [runSucceeded, aggregatable, () => createAggregation.isPending.value],
  ([succeeded, available, pending]) => {
    const runId = activeRunId.value
    if (!succeeded || available.length === 0 || autoCreateAttempted || pending || runId === null) {
      return
    }
    autoCreateAttempted = true
    void createAggregation
      .mutateAsync({
        runId,
        methodExecutionIds: available.map((execution) => execution.id),
        strategy: 'reference_v1',
      })
      .then((result) => {
        createdAggregationId.value = result.aggregation.id
      })
      .catch(() => {
        // createAggregation.isError/.error already reflect this; shown below.
      })
  },
)

let workingSetFor: string | null = null
watch(
  [aggregationDone, createdAggregationId],
  ([done, aggregationId]) => {
    if (!done || aggregationId === null || workingSetFor === aggregationId) return
    workingSetFor = aggregationId
    void setWorking.mutateAsync(aggregationId).then(() => {
      activeRunId.value = null
      autoCreateAttempted = false
      createdAggregationId.value = null
    })
  },
  { immediate: true },
)

// The registry can hold methods this deployment has no usable configuration for yet (e.g. a lookup
// method with no compiled snapshot) — the server rejects the whole run at creation, naming exactly
// one offending method per attempt. Guided mode has no configuration step of its own (D27: one
// sequential flow, no decisions), so it reruns without that one method and tries again, converging
// on whatever subset this deployment can actually run rather than failing outright every time.
const METHOD_NAME_IN_ERROR = /method '([^']+)'/
function unusableMethodFrom(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.code !== 'validation_error') return null
  const reason = error.details['reason']
  return typeof reason === 'string' ? (METHOD_NAME_IN_ERROR.exec(reason)?.[1] ?? null) : null
}

async function startGenerate(): Promise<void> {
  const snapshotId = latestReady.value?.id
  const allMethods = methods.data.value
  if (snapshotId === undefined || !canGenerate.value || allMethods === undefined) return
  autoCreateAttempted = false
  createdAggregationId.value = null
  workingSetFor = null
  const excluded = new Set<string>()
  for (let attempt = 0; attempt <= allMethods.length; attempt += 1) {
    const methodConfigs = allMethods
      .filter((method) => !excluded.has(method.name))
      .map((method) => ({ name: method.name, enabled: true, config: {} }))
    if (methodConfigs.length === 0) return // createRun.isError/.error already reflect the last attempt.
    try {
      const run = await createRun.mutateAsync({ snapshotId, config: { methods: methodConfigs } })
      activeRunId.value = run.id
      return
    } catch (error) {
      const unusable = unusableMethodFrom(error)
      if (unusable === null || excluded.has(unusable)) return // createRun.isError/.error already reflect this.
      excluded.add(unusable)
      createRun.reset()
    }
  }
}

function retryGenerate(): void {
  activeRunId.value = null
  autoCreateAttempted = false
  createdAggregationId.value = null
  createAggregation.reset()
  createRun.reset()
}

const generateHint = computed(() => {
  if (createRun.isPending.value) return t('genderTagging.generate.starting')
  if (createRun.isError.value) return generateErrorText.value
  if (activeRunId.value === null) {
    return isDone.value
      ? t('genderTagging.generate.doneHint', {
          count: n(workingAggregation.data.value?.method_execution_ids.length ?? 0, 'integer'),
        })
      : t('genderTagging.generate.hint')
  }
  if (aggregationFailed.value) return generateErrorText.value
  if (!runEnded.value) {
    return t('genderTagging.generate.runProgress', {
      done: n(
        (activeExecutions.data.value ?? []).filter((execution) =>
          AGGREGATABLE_EXECUTION_STATUSES.has(execution.status),
        ).length,
        'integer',
      ),
      total: n(methods.data.value?.length ?? 0, 'integer'),
    })
  }
  if (runFailed.value) return t('genderTagging.generate.runFailed')
  return t('genderTagging.generate.aggregating')
})

const generateErrorText = computed(() => {
  const error = createRun.error.value ?? createAggregation.error.value
  if (error instanceof ApiError && error.code === 'network_error') {
    return t('genderTagging.generate.errors.network')
  }
  // The aggregation step is always automatic here (D27: no manual selection UI), so this is
  // always the same "auto" case `AggregationSection.vue` distinguishes from a manual one.
  if (error instanceof ApiError && error.code === 'resource_conflict') {
    return t('aggregations.errors.autoNotAggregatable')
  }
  return t('genderTagging.generate.errors.generic')
})

const generateBusy = computed(
  () =>
    createRun.isPending.value ||
    (activeRunId.value !== null && !isDone.value && !runFailed.value && !aggregationFailed.value),
)
const canStartGenerate = computed(
  () => canGenerate.value && latestReady.value !== null && !generateBusy.value,
)
const showRetry = computed(() => runFailed.value || aggregationFailed.value)

const exportFormat = ref<ExportFormat>('tei')
const createExport = useCreateExport()
const exportError = computed(() => {
  const error = createExport.error.value
  if (!createExport.isError.value || error === null) return ''
  if (error instanceof ApiError && error.code === 'network_error') {
    return t('export.new.errors.network')
  }
  return t('export.new.errors.generic')
})
const canSubmitExport = computed(
  () =>
    isDone.value &&
    !createExport.isPending.value &&
    (exportFormat.value !== 'tei' || teiPossible.value),
)

async function submitExport(): Promise<void> {
  const aggregation = workingAggregation.data.value
  const workingId = workingAggregationId.value
  if (!canSubmitExport.value || aggregation === undefined || workingId === null) return
  const created = await createExport
    .mutateAsync({
      run_id: aggregation.run_id,
      aggregation_execution_id: workingId,
      format: exportFormat.value,
      label_source_policy: 'machine_aggregation',
      human_resp_id: '#editor',
      ...(exportFormat.value === 'tei' ? { tei_profile: 'tei_p5_gender_v1' } : {}),
    })
    .catch(() => null)
  if (created === null) return
  void router.push({
    name: 'exportDetail',
    params: { projectId: projectId.value, runId: aggregation.run_id, exportId: created.id },
  })
}
</script>

<template>
  <main class="gender-tagging app-page-frame">
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="app-card"
      announcement="polite"
      >{{ t('projects.loading') }}</AppFeedback
    >
    <AppFeedback
      v-else-if="session.status === 'error'"
      class="app-card"
      tone="critical"
      announcement="assertive"
    >
      {{ t('projects.sessionLoadError') }}
      <template #actions
        ><AppButton variant="ghost" @click="retrySession">{{
          t('projects.retry')
        }}</AppButton></template
      >
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <AppFeedback v-if="project.isPending.value" class="app-card" announcement="polite">
        {{ t('projects.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="project.isError.value"
        class="app-card"
        tone="critical"
        announcement="assertive"
      >
        {{ t('data.projectLoadError') }}
        <template #actions
          ><AppButton variant="ghost" @click="project.refetch()">{{
            t('projects.retry')
          }}</AppButton></template
        >
      </AppFeedback>
      <template v-else-if="project.data.value">
        <header class="app-page-heading">
          <h1 class="app-page-heading__title">{{ project.data.value.display_name }}</h1>
        </header>
        <div class="gender-tagging-card app-card app-card--sectioned">
          <ProjectOverviewSection>
            <dl class="gender-tagging-facts">
              <div>
                <dt>{{ t('projects.overview.slug') }}</dt>
                <dd>{{ project.data.value.slug }}</dd>
              </div>
              <div>
                <dt>{{ t('projects.overview.role') }}</dt>
                <dd>{{ roleLabel(project.data.value.current_user_role) }}</dd>
              </div>
              <div>
                <dt>{{ t('projects.overview.team') }}</dt>
                <dd>{{ project.data.value.team.display_name }}</dd>
              </div>
            </dl>
          </ProjectOverviewSection>

          <ProjectOverviewSection
            :eyebrow="t('genderTagging.step', { number: 1 })"
            :title="t('data.importAction')"
          >
            <p class="gender-tagging-hint">
              {{
                latestReady
                  ? t('genderTagging.import.doneHint', {
                      count: n(latestReady.record_count ?? 0, 'integer'),
                    })
                  : t('genderTagging.import.hint')
              }}
            </p>
            <div v-show="importOpen && canImport" class="gender-tagging-import-panel">
              <SnapshotImportForm
                v-if="importMounted && session.user"
                :key="`${session.user.id}:${projectId}:${importInstance}`"
                :project-id="projectId"
              />
            </div>
            <AppButton
              v-if="canImport"
              variant="ghost"
              :aria-expanded="importOpen"
              @click="toggleImport"
            >
              {{ importOpen ? t('data.hideImport') : t('data.importAction') }}
            </AppButton>
          </ProjectOverviewSection>

          <ProjectOverviewSection
            :eyebrow="t('genderTagging.step', { number: 2 })"
            :title="t('genderTagging.generate.title')"
          >
            <p class="gender-tagging-hint">{{ generateHint }}</p>
            <div class="gender-tagging-actions">
              <AppButton
                variant="solid"
                :disabled="!canStartGenerate"
                @click="startGenerate"
              >
                {{
                  isDone
                    ? t('genderTagging.generate.again')
                    : t('genderTagging.generate.title')
                }}
              </AppButton>
              <AppButton v-if="showRetry" variant="ghost" @click="retryGenerate">
                {{ t('projects.retry') }}
              </AppButton>
            </div>
          </ProjectOverviewSection>

          <ProjectOverviewSection
            v-if="isDone"
            :eyebrow="t('genderTagging.step', { number: 3 })"
            :title="t('genderTagging.review.title')"
          >
            <p class="gender-tagging-hint">{{ t('genderTagging.review.hint') }}</p>
            <AppButton
              variant="solid"
              :to="{
                name: 'review',
                params: {
                  projectId,
                  runId: workingAggregation.data.value?.run_id,
                  aggregationId: workingAggregationId,
                },
              }"
            >
              {{ t('genderTagging.review.open') }}
            </AppButton>
          </ProjectOverviewSection>

          <ProjectOverviewSection
            v-if="isDone"
            :eyebrow="t('genderTagging.step', { number: 4 })"
            :title="t('genderTagging.export.title')"
          >
            <p class="gender-tagging-hint">{{ t('genderTagging.export.hint') }}</p>
            <form class="gender-tagging-export-form" novalidate @submit.prevent="submitExport">
              <AppSelectField
                id="gender-tagging-export-format"
                v-model="exportFormat"
                class="gender-tagging-export-field"
                :label="t('export.new.format')"
              >
                <option value="tei">{{ t('export.new.formats.tei') }}</option>
                <option value="json">{{ t('export.new.formats.json') }}</option>
                <option value="csv">{{ t('export.new.formats.csv') }}</option>
              </AppSelectField>
              <p v-if="exportFormat === 'tei' && !teiPossible" role="alert" class="gender-tagging-error">
                {{ t('export.new.teiNotPossible') }}
              </p>
              <p v-if="exportError" role="alert" class="gender-tagging-error">{{ exportError }}</p>
              <AppButton type="submit" variant="solid" :disabled="!canSubmitExport">
                {{ createExport.isPending.value ? t('export.new.submitting') : t('export.new.submit') }}
              </AppButton>
            </form>
          </ProjectOverviewSection>
        </div>
      </template>
    </template>
  </main>
</template>

<style scoped>
.gender-tagging {
  container: gender-tagging / inline-size;
}

.gender-tagging-facts {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-2) var(--space-6);
  margin: 0;
}

@container gender-tagging (min-width: 30rem) {
  .gender-tagging-facts {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.gender-tagging-facts dt {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.gender-tagging-facts dd {
  margin: 0;
}

.gender-tagging-hint {
  margin: 0 0 var(--space-3);
  color: var(--text-secondary);
}

.gender-tagging-import-panel {
  margin-block-end: var(--space-3);
}

.gender-tagging-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.gender-tagging-export-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.gender-tagging-export-field {
  min-inline-size: 12rem;
}

.gender-tagging-error {
  margin: 0;
  color: var(--critical-text);
}
</style>
