<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useApiClient } from '@/composables/useApiClient'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useArtifactRouteContext } from '@/composables/useArtifactRouteContext'
import LifecycleStatus from '@/components/domain/LifecycleStatus.vue'

import { downloadExport, saveDownload, type DownloadedExport } from './exportDownload'
import { useExport, useExportManifest } from './useExports'

const { t, d, n } = useI18n()
const client = useApiClient()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const runId = useRouteParam('runId')
const exportId = useRouteParam('exportId')

const query = useExport(exportId, isSignedIn)
const context = useArtifactRouteContext(exportId, query)
const item = { ...query, ...context }
const isCompleted = computed(() => isSignedIn.value && item.data.value?.status === 'completed')
const manifest = useExportManifest(exportId, isCompleted)

// Downloading also hashes what arrived, so the result can be compared with the manifest's checksum.
const downloading = ref(false)
const downloadError = ref('')
const result = ref<DownloadedExport | null>(null)
const expected = ref('')
let downloadController: AbortController | null = null

function abortDownload(): void {
  downloadController?.abort()
  downloadController = null
  downloading.value = false
}

function clearDownload(): void {
  abortDownload()
  downloadError.value = ''
  result.value = null
  expected.value = ''
}

watch(
  () =>
    [
      session.principalRevision,
      exportId.value,
      projectId.value,
      runId.value,
      context.valid.value,
      context.isError.value,
      session.canUsePrivateNavigation,
      item.error.value,
      manifest.error.value,
    ] as const,
  (
    [
      revision,
      resourceId,
      routeProject,
      routeRun,
      valid,
      invalid,
      canRead,
      itemError,
      manifestError,
    ],
    previous,
  ) => {
    const denied = [itemError, manifestError].some(
      (error) => error instanceof ApiError && [401, 403, 404].includes(error.status ?? 0),
    )
    if (
      denied ||
      invalid ||
      (previous &&
        (previous[0] !== revision ||
          previous[1] !== resourceId ||
          previous[2] !== routeProject ||
          previous[3] !== routeRun))
    )
      clearDownload()
    else if (!valid || !canRead) abortDownload()
  },
  { flush: 'sync' },
)
onScopeDispose(clearDownload)

async function download(): Promise<void> {
  const current = item.data.value
  if (!current || !isCompleted.value || downloading.value || !session.canUsePrivateNavigation)
    return
  const principalRevision = session.principalRevision
  const routeProject = projectId.value
  const routeRun = runId.value
  const snapshotId = context.snapshotId.value
  const controller = new AbortController()
  downloadController = controller
  const ownsDownload = () =>
    downloadController === controller &&
    !controller.signal.aborted &&
    session.principalRevision === principalRevision &&
    session.canUsePrivateNavigation &&
    context.valid.value &&
    projectId.value === routeProject &&
    runId.value === routeRun &&
    context.snapshotId.value === snapshotId &&
    exportId.value === current.id &&
    item.data.value?.id === current.id
  downloading.value = true
  downloadError.value = ''
  try {
    const downloaded = await downloadExport(client, current.id, current.format, controller.signal)
    if (!ownsDownload()) return
    result.value = downloaded
    saveDownload(downloaded)
  } catch (error) {
    if (!ownsDownload()) return
    if (error instanceof ApiError && [401, 403, 404].includes(error.status ?? 0)) {
      result.value = null
      expected.value = ''
    }
    downloadError.value =
      error instanceof ApiError && error.code === 'resource_not_found'
        ? t('export.detail.errors.notFound')
        : t('export.detail.errors.generic')
  } finally {
    if (downloadController === controller) {
      downloading.value = false
      downloadController = null
    }
  }
}

// The download is checked against the manifest the server persisted for this export: the bytes must
// have the checksum and size the manifest records for the (one) output. An export with several outputs
// downloads as the manifest itself, so there is nothing to compare it to.
type ManifestVerdict = 'none' | 'match' | 'mismatch' | 'notApplicable'
const manifestVerdict = computed<ManifestVerdict>(() => {
  const downloaded = result.value
  const outputs = manifest.data.value?.outputs
  if (!downloaded || !outputs) return 'none'
  if (downloaded.manifest || outputs.length !== 1) return 'notApplicable'
  const [only] = outputs
  return only?.sha256 === downloaded.sha256 && only.byte_size === downloaded.byteSize
    ? 'match'
    : 'mismatch'
})

const SHA256 = /^[0-9a-f]{64}$/
const normalized = computed(() => expected.value.trim().toLowerCase())
type Verdict = 'none' | 'malformed' | 'match' | 'mismatch'
const verdict = computed<Verdict>(() => {
  if (normalized.value === '' || !result.value) return 'none'
  if (!SHA256.test(normalized.value)) return 'malformed'
  return normalized.value === result.value.sha256 ? 'match' : 'mismatch'
})
</script>

<template>
  <main class="export-detail app-page-frame">
    <RouterLink
      v-if="context.valid.value"
      class="export-detail-back"
      :to="{ name: 'exports', params: { projectId, runId } }"
    >
      {{ t('export.detail.backToList') }}
    </RouterLink>
    <header class="export-detail-page-heading app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="export-detail-title app-page-heading__title">
          {{ t('export.detail.title') }}
        </h1>
        <p v-if="isSignedIn && item.data.value" class="export-detail-status" role="status">
          <LifecycleStatus :status="item.data.value.status" />
        </p>
      </div>
    </header>

    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="app-card"
      announcement="polite"
    >
      {{ t('runs.loading') }}
    </AppFeedback>
    <AppFeedback
      v-else-if="session.status === 'error'"
      class="app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('projects.sessionLoadError') }}
      <template #actions>
        <AppButton type="button" variant="ghost" @click="retrySession">
          {{ t('runs.retry') }}
        </AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <AppFeedback v-if="item.isPending.value" class="app-card" announcement="polite">
        {{ t('runs.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="item.isError.value"
        class="app-card"
        announcement="assertive"
        tone="critical"
      >
        {{ t('export.detail.loadError') }}
        <template #actions>
          <AppButton
            class="export-detail-retry"
            type="button"
            variant="ghost"
            :disabled="item.isFetching.value"
            @click="() => item.refetch()"
          >
            {{ t('runs.retry') }}
          </AppButton>
        </template>
      </AppFeedback>
      <template v-else-if="item.data.value">
        <div
          v-if="item.data.value.failure_class || item.data.value.failure_diagnostic"
          class="export-detail-failure app-card"
        >
          <p v-if="item.data.value.failure_class" class="export-detail-failure-class">
            {{ item.data.value.failure_class }}
          </p>
          <p v-if="item.data.value.failure_diagnostic">
            {{ item.data.value.failure_diagnostic }}
          </p>
        </div>

        <section class="export-detail-block app-card" aria-labelledby="export-params-heading">
          <h2 id="export-params-heading" class="export-detail-heading">
            {{ t('export.detail.parameters') }}
          </h2>
          <dl class="export-detail-facts app-fact-list">
            <div class="export-detail-fact app-fact-list__item">
              <dt>{{ t('export.item.format') }}</dt>
              <dd class="export-detail-token">{{ item.data.value.format }}</dd>
            </div>
            <div class="export-detail-fact app-fact-list__item">
              <dt>{{ t('export.item.policy') }}</dt>
              <dd class="export-detail-token">
                {{ item.data.value.label_source_policy ?? 'machine_aggregation' }}
              </dd>
            </div>
            <div v-if="item.data.value.tei_profile" class="export-detail-fact app-fact-list__item">
              <dt>{{ t('export.item.profile') }}</dt>
              <dd class="export-detail-token">{{ item.data.value.tei_profile }}</dd>
            </div>
            <div
              v-if="item.data.value.format === 'tei'"
              class="export-detail-fact app-fact-list__item"
            >
              <dt>{{ t('export.detail.resp') }}</dt>
              <dd class="export-detail-token">{{ item.data.value.human_resp_id }}</dd>
            </div>
            <div class="export-detail-fact app-fact-list__item">
              <dt>{{ t('aggregations.detail.created') }}</dt>
              <dd>{{ d(new Date(item.data.value.created_at), 'timestamp') }}</dd>
            </div>
            <div v-if="item.data.value.finished_at" class="export-detail-fact app-fact-list__item">
              <dt>{{ t('aggregations.detail.finished') }}</dt>
              <dd>{{ d(new Date(item.data.value.finished_at), 'timestamp') }}</dd>
            </div>
            <div class="export-detail-fact app-fact-list__item">
              <dt>{{ t('evaluation.detail.aggregation') }}</dt>
              <dd>
                <RouterLink
                  class="export-detail-aggregation"
                  :to="{
                    name: 'aggregationDetail',
                    params: {
                      projectId,
                      runId,
                      aggregationId: item.data.value.aggregation_execution_id,
                    },
                  }"
                >
                  {{ t('evaluation.detail.openAggregation') }}
                </RouterLink>
              </dd>
            </div>
          </dl>
        </section>

        <p
          v-if="!isCompleted && !['failed', 'cancelled'].includes(item.data.value.status)"
          class="export-detail-waiting app-card"
          role="status"
        >
          {{ t('export.detail.waiting') }}
        </p>

        <section
          v-if="isCompleted"
          class="export-detail-block export-detail-manifest-section app-card"
          aria-labelledby="export-manifest-heading"
        >
          <h2 id="export-manifest-heading" class="export-detail-heading">
            {{ t('export.detail.manifest.title') }}
          </h2>
          <p class="export-detail-note">{{ t('export.detail.manifest.note') }}</p>
          <AppFeedback v-if="manifest.isPending.value" announcement="polite">
            {{ t('runs.loading') }}
          </AppFeedback>
          <AppFeedback v-else-if="manifest.isError.value" announcement="assertive" tone="critical">
            <p class="export-detail-manifest-error">
              {{ t('export.detail.manifest.loadError') }}
            </p>
            <template #actions>
              <AppButton
                type="button"
                variant="ghost"
                :disabled="manifest.isFetching.value"
                @click="() => manifest.refetch()"
              >
                {{ t('runs.retry') }}
              </AppButton>
            </template>
          </AppFeedback>
          <template v-else-if="manifest.data.value">
            <dl class="export-detail-facts app-fact-list">
              <div class="export-detail-fact app-fact-list__item">
                <dt>{{ t('export.detail.sourceSnapshot') }}</dt>
                <dd>
                  <code class="export-detail-hash export-detail-source-hash">{{
                    manifest.data.value.source_snapshot_sha256
                  }}</code>
                </dd>
              </div>
              <div class="export-detail-fact app-fact-list__item">
                <dt>{{ t('export.detail.manifest.generated') }}</dt>
                <dd>{{ d(new Date(manifest.data.value.generated_at), 'timestamp') }}</dd>
              </div>
            </dl>
            <table class="export-detail-outputs export-detail-manifest-outputs">
              <caption class="export-detail-caption">
                {{
                  t('export.detail.outputs')
                }}
              </caption>
              <thead>
                <tr>
                  <th scope="col">{{ t('export.detail.file') }}</th>
                  <th scope="col">{{ t('export.detail.size') }}</th>
                  <th scope="col">{{ t('export.detail.checksum') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="output in manifest.data.value.outputs" :key="output.logical_name">
                  <th scope="row">{{ output.logical_name }}</th>
                  <td>{{ t('export.detail.bytes', { size: n(output.byte_size, 'integer') }) }}</td>
                  <td>
                    <code class="export-detail-hash">{{ output.sha256 }}</code>
                  </td>
                </tr>
              </tbody>
            </table>
          </template>
        </section>

        <section
          v-if="isCompleted"
          class="export-detail-block app-card"
          aria-labelledby="export-download-heading"
        >
          <h2 id="export-download-heading" class="export-detail-heading">
            {{ t('export.detail.download') }}
          </h2>
          <p class="export-detail-note">{{ t('export.detail.downloadNote') }}</p>
          <AppButton
            class="export-detail-download"
            type="button"
            :disabled="downloading"
            @click="download"
          >
            {{ downloading ? t('export.detail.downloading') : t('export.detail.downloadButton') }}
          </AppButton>
          <p v-if="downloadError" role="alert" class="export-detail-error">{{ downloadError }}</p>

          <div v-if="result" class="export-detail-result" role="status">
            <dl class="export-detail-facts app-fact-list">
              <div class="export-detail-fact app-fact-list__item">
                <dt>{{ t('export.detail.file') }}</dt>
                <dd>{{ result.filename }}</dd>
              </div>
              <div class="export-detail-fact app-fact-list__item">
                <dt>{{ t('export.detail.size') }}</dt>
                <dd>{{ t('export.detail.bytes', { size: n(result.byteSize, 'integer') }) }}</dd>
              </div>
              <div class="export-detail-fact app-fact-list__item">
                <dt>{{ t('export.detail.checksum') }}</dt>
                <dd>
                  <code class="export-detail-hash">{{ result.sha256 }}</code>
                </dd>
              </div>
            </dl>

            <p v-if="result.manifest" class="export-detail-note">
              {{ t('export.detail.manifestReceived') }}
            </p>
            <p class="export-detail-manifest-verdict" role="status">
              <span v-if="manifestVerdict === 'match'" class="export-detail-verdict--match">{{
                t('export.detail.manifestVerdict.match')
              }}</span>
              <span
                v-else-if="manifestVerdict === 'mismatch'"
                class="export-detail-verdict--mismatch"
                >{{ t('export.detail.manifestVerdict.mismatch') }}</span
              >
              <span v-else-if="manifestVerdict === 'notApplicable'" class="export-detail-note">{{
                t('export.detail.manifestVerdict.notApplicable')
              }}</span>
            </p>

            <div class="export-detail-verify">
              <AppTextField
                id="export-expected"
                v-model="expected"
                :label="t('export.detail.verifyLabel')"
                autocomplete="off"
                :spellcheck="false"
                aria-describedby="export-verify-result"
              />
              <p id="export-verify-result" class="export-detail-verdict" role="status">
                <template v-if="verdict === 'match'">
                  <span class="export-detail-verdict--match">{{
                    t('export.detail.verdict.match')
                  }}</span>
                </template>
                <template v-else-if="verdict === 'mismatch'">
                  <span class="export-detail-verdict--mismatch">{{
                    t('export.detail.verdict.mismatch')
                  }}</span>
                </template>
                <template v-else-if="verdict === 'malformed'">
                  <span class="export-detail-verdict--mismatch">{{
                    t('export.detail.verdict.malformed')
                  }}</span>
                </template>
              </p>
            </div>
          </div>
        </section>
      </template>
    </template>
  </main>
</template>

<style scoped>
.export-detail {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-4);
}

.export-detail > * {
  max-width: 100%;
}

.export-detail-back {
  align-self: flex-start;
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.export-detail-page-heading {
  width: 100%;
  margin-block-end: 0;
}

.export-detail-status {
  margin: 0;
  font-weight: var(--weight-semibold);
}

.export-detail-failure,
.export-detail-error {
  margin: 0;
  color: var(--critical-text);
}

.export-detail-failure p {
  margin: 0;
}

.export-detail-failure,
.export-detail-waiting {
  width: 100%;
}

.export-detail-failure-class {
  font-weight: var(--weight-semibold);
}

.export-detail-block {
  display: flex;
  width: 100%;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.export-detail-heading {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.export-detail-facts {
  width: 100%;
  --app-fact-list-label-width: 11rem;
}

.export-detail-token {
  font-family: var(--font-mono, ui-monospace, monospace);
}

.export-detail-hash {
  font-size: var(--font-size-small);
}

.export-detail-aggregation {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.export-detail-waiting,
.export-detail-note {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.export-detail-result {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: var(--space-3);
  padding-block-start: var(--space-3);
  border-block-start: 1px solid var(--border);
}

.export-detail-outputs {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-small);
}

.export-detail-outputs th,
.export-detail-outputs td {
  padding: var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--grid);
  text-align: left;
  overflow-wrap: anywhere;
}

.export-detail-caption {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.export-detail-verify {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--font-size-small);
}

.export-detail-verify {
  --field-label-color: var(--text-primary);
  --field-control-width: 100%;
  --field-control-font: var(--font-size-small) var(--font-mono, ui-monospace, monospace);
}

.export-detail-verdict {
  margin: 0;
  font-weight: var(--weight-semibold);
}

.export-detail-verdict--match {
  color: var(--good);
}

.export-detail-verdict--mismatch {
  color: var(--critical-text);
}
</style>
