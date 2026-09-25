<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import { useApiClient } from '@/composables/useApiClient'
import { useRequireSession, useRouteParam } from '@/composables/useRequireSession'
import { useStatusLabel } from '@/features/runs/useStatusLabel'

import { downloadExport, saveDownload, type DownloadedExport } from './exportDownload'
import { useExport, useExportManifest } from './useExports'

const { t, d, n } = useI18n()
const label = useStatusLabel()
const client = useApiClient()
const { session, isSignedIn, retrySession } = useRequireSession()

const projectId = useRouteParam('projectId')
const runId = useRouteParam('runId')
const exportId = useRouteParam('exportId')

const item = useExport(exportId, isSignedIn)
const isCompleted = computed(() => item.data.value?.status === 'completed')
const manifest = useExportManifest(exportId, isCompleted)

// Downloading also hashes what arrived, so the result can be compared with the manifest's checksum.
const downloading = ref(false)
const downloadError = ref('')
const result = ref<DownloadedExport | null>(null)
const expected = ref('')

async function download(): Promise<void> {
  const current = item.data.value
  if (!current || downloading.value) return
  downloading.value = true
  downloadError.value = ''
  try {
    const downloaded = await downloadExport(client, current.id, current.format)
    result.value = downloaded
    saveDownload(downloaded)
  } catch (error) {
    downloadError.value =
      error instanceof ApiError && error.code === 'resource_not_found'
        ? t('export.detail.errors.notFound')
        : t('export.detail.errors.generic')
  } finally {
    downloading.value = false
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
  <main class="export-detail">
    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('runs.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="export-detail-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('runs.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <RouterLink
        class="export-detail-back"
        :to="{ name: 'exports', params: { projectId, runId } }"
      >
        {{ t('export.detail.backToList') }}
      </RouterLink>

      <p v-if="item.isPending.value" role="status">{{ t('runs.loading') }}</p>
      <div v-else-if="item.isError.value" class="export-detail-load-error">
        <p role="alert">{{ t('export.detail.loadError') }}</p>
        <AppButton class="export-detail-retry" type="button" @click="() => item.refetch()">
          {{ t('runs.retry') }}
        </AppButton>
      </div>
      <template v-else-if="item.data.value">
        <h1 class="export-detail-title">{{ t('export.detail.title') }}</h1>
        <p class="export-detail-status" role="status">
          <span :class="`export-detail-status--${item.data.value.status}`">{{
            label(item.data.value.status)
          }}</span>
        </p>
        <div
          v-if="item.data.value.failure_class || item.data.value.failure_diagnostic"
          class="export-detail-failure"
        >
          <p v-if="item.data.value.failure_class" class="export-detail-failure-class">
            {{ item.data.value.failure_class }}
          </p>
          <p v-if="item.data.value.failure_diagnostic">
            {{ item.data.value.failure_diagnostic }}
          </p>
        </div>

        <section class="export-detail-block" aria-labelledby="export-params-heading">
          <h2 id="export-params-heading" class="export-detail-heading">
            {{ t('export.detail.parameters') }}
          </h2>
          <dl class="export-detail-facts">
            <div class="export-detail-fact">
              <dt>{{ t('export.item.format') }}</dt>
              <dd class="export-detail-token">{{ item.data.value.format }}</dd>
            </div>
            <div class="export-detail-fact">
              <dt>{{ t('export.item.policy') }}</dt>
              <dd class="export-detail-token">
                {{ item.data.value.label_source_policy ?? 'machine_aggregation' }}
              </dd>
            </div>
            <div v-if="item.data.value.tei_profile" class="export-detail-fact">
              <dt>{{ t('export.item.profile') }}</dt>
              <dd class="export-detail-token">{{ item.data.value.tei_profile }}</dd>
            </div>
            <div v-if="item.data.value.format === 'tei'" class="export-detail-fact">
              <dt>{{ t('export.detail.resp') }}</dt>
              <dd class="export-detail-token">{{ item.data.value.human_resp_id }}</dd>
            </div>
            <div class="export-detail-fact">
              <dt>{{ t('aggregations.detail.created') }}</dt>
              <dd>{{ d(new Date(item.data.value.created_at), 'timestamp') }}</dd>
            </div>
            <div v-if="item.data.value.finished_at" class="export-detail-fact">
              <dt>{{ t('aggregations.detail.finished') }}</dt>
              <dd>{{ d(new Date(item.data.value.finished_at), 'timestamp') }}</dd>
            </div>
            <div class="export-detail-fact">
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
          class="export-detail-waiting"
          role="status"
        >
          {{ t('export.detail.waiting') }}
        </p>

        <section
          v-if="isCompleted"
          class="export-detail-block export-detail-manifest-section"
          aria-labelledby="export-manifest-heading"
        >
          <h2 id="export-manifest-heading" class="export-detail-heading">
            {{ t('export.detail.manifest.title') }}
          </h2>
          <p class="export-detail-note">{{ t('export.detail.manifest.note') }}</p>
          <p v-if="manifest.isPending.value" role="status">{{ t('runs.loading') }}</p>
          <div v-else-if="manifest.isError.value" class="export-detail-load-error">
            <p role="alert" class="export-detail-manifest-error">
              {{ t('export.detail.manifest.loadError') }}
            </p>
            <AppButton type="button" @click="() => manifest.refetch()">
              {{ t('runs.retry') }}
            </AppButton>
          </div>
          <template v-else-if="manifest.data.value">
            <dl class="export-detail-facts">
              <div class="export-detail-fact">
                <dt>{{ t('export.detail.sourceSnapshot') }}</dt>
                <dd>
                  <code class="export-detail-hash export-detail-source-hash">{{
                    manifest.data.value.source_snapshot_sha256
                  }}</code>
                </dd>
              </div>
              <div class="export-detail-fact">
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
          class="export-detail-block"
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
            <dl class="export-detail-facts">
              <div class="export-detail-fact">
                <dt>{{ t('export.detail.file') }}</dt>
                <dd>{{ result.filename }}</dd>
              </div>
              <div class="export-detail-fact">
                <dt>{{ t('export.detail.size') }}</dt>
                <dd>{{ t('export.detail.bytes', { size: n(result.byteSize, 'integer') }) }}</dd>
              </div>
              <div class="export-detail-fact">
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
              <label for="export-expected">{{ t('export.detail.verifyLabel') }}</label>
              <input
                id="export-expected"
                v-model="expected"
                type="text"
                autocomplete="off"
                spellcheck="false"
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
  padding: var(--space-8) var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
  max-width: 56rem;
}

.export-detail > * {
  max-width: 100%;
}

.export-detail-back {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.export-detail-title {
  margin: 0;
  font-size: var(--font-size-page);
  line-height: var(--line-height-page);
}

.export-detail-status {
  margin: 0;
  font-weight: var(--weight-semibold);
}

.export-detail-status--completed {
  color: var(--good);
}

.export-detail-status--failed {
  color: var(--critical-text);
}

.export-detail-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.export-detail-load-error p,
.export-detail-failure,
.export-detail-error {
  margin: 0;
  color: var(--critical-text);
}

.export-detail-failure p {
  margin: 0;
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
  display: grid;
  width: 100%;
  gap: var(--space-2);
  margin: 0;
}

.export-detail-fact {
  display: grid;
  grid-template-columns: 11rem 1fr;
  gap: var(--space-3);
}

.export-detail-fact dt {
  color: var(--text-secondary);
}

.export-detail-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
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
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
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

.export-detail-verify input {
  width: 100%;
  font: var(--font-size-small) var(--font-mono, ui-monospace, monospace);
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
