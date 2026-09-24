<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppListbox from '@/components/base/AppListbox.vue'
import { useSessionStore } from '@/stores/session'

import {
  isPersonRegisterHeader,
  PERSON_REGISTER_COLUMNS,
  readCsvHeader,
} from './personRegisterProfile'
import { useProject } from './useProjects'
import {
  useImportSnapshot,
  useSnapshotStatus,
  useSnapshotUploadLimits,
  type SourceFormat,
  type SourcePackaging,
} from './useSnapshotImport'

const { t, n } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()

// Wait for the one loading -> ready transition before deciding, exactly like /change-password and
// /projects: session.initialize() is still pending on every fresh page load, cookie or not.
watch(
  () => session.status,
  (status) => {
    if (status === 'ready' && !session.isSignedIn) {
      void router.replace({ name: 'login', query: { redirect: route.fullPath } })
    }
  },
  { immediate: true },
)

function retrySession(): void {
  void session.initialize()
}

const isSignedIn = computed(() => session.status === 'ready' && session.isSignedIn)

// A single, non-repeating :projectId segment is always a plain string at runtime; normalized here
// only because vue-router's generic param type also allows string[].
const projectId = computed(() => {
  const raw = route.params.projectId
  return Array.isArray(raw) ? (raw[0] ?? '') : (raw ?? '')
})

const project = useProject(projectId, isSignedIn)
// Import is a project-scoped operator action (backend: ProjectAccessGuard requires
// ProjectRole.operator here), not the global operator/admin role D6 gives project *creation*.
const canImport = computed(() => project.data.value?.current_user_role === 'operator')

const sourceFormatOptions: { value: SourceFormat; label: string }[] = [
  { value: 'tei', label: 'TEI-XML' },
  { value: 'csv', label: 'CSV' },
  { value: 'xlsx', label: 'XLSX' },
  { value: 'json', label: 'JSON' },
]
const sourceFormat = ref<SourceFormat>('tei')
// Only TEI can arrive as several files or as an archive; the backend rejects any other
// combination ("tabular imports require packaging='single'"), so the choice is not offered.
const packaging = ref<SourcePackaging>('single')
const isTei = computed(() => sourceFormat.value === 'tei')
const packagingOptions = computed<{ value: SourcePackaging; label: string }[]>(() => [
  { value: 'single', label: t('projects.import.packaging.single') },
  { value: 'loose', label: t('projects.import.packaging.loose') },
  { value: 'zip', label: t('projects.import.packaging.zip') },
  { value: 'tar_gz', label: t('projects.import.packaging.tarGz') },
])
const isArchive = computed(() => packaging.value === 'zip' || packaging.value === 'tar_gz')

const files = ref<File[]>([])
// A new key remounts the file input, which is the only way to clear a native file selection.
const fileInputKey = ref(0)

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  files.value = Array.from(input.files ?? [])
}

watch(sourceFormat, (format) => {
  if (format !== 'tei') packaging.value = 'single'
})
// A selection made for one packaging is not valid for another (one file vs. several).
watch([sourceFormat, packaging], () => {
  files.value = []
  fileInputKey.value += 1
})

const limits = useSnapshotUploadLimits(isSignedIn)
const mebibytes = (bytes: number): string => n(bytes / (1024 * 1024), 'decimal')

// The bounds are the server's to enforce (a 413 is still handled below); checking them first only
// saves a doomed upload and lets the message name the problem rather than just the request.
const sizeProblem = computed<'part' | 'total' | null>(() => {
  const bounds = limits.data.value
  if (!bounds) return null
  if (files.value.some((file) => file.size > bounds.max_upload_part_bytes)) return 'part'
  const total = files.value.reduce((sum, file) => sum + file.size, 0)
  return total > bounds.max_total_upload_bytes ? 'total' : null
})
// The delivery choice decides how the server reads the bytes: a ZIP sent as "single file" is parsed
// as XML and fails only after the snapshot exists. The file name is enough to catch that up front.
const isZipName = (name: string): boolean => name.toLowerCase().endsWith('.zip')
const isTarGzName = (name: string): boolean => /.(tar.gz|tgz)$/i.test(name)
const packagingProblem = computed<'looksLikeArchive' | 'notAnArchive' | null>(() => {
  if (!isTei.value || files.value.length === 0) return null
  const names = files.value.map((file) => file.name)
  if (packaging.value === 'single' || packaging.value === 'loose') {
    return names.some((name) => isZipName(name) || isTarGzName(name)) ? 'looksLikeArchive' : null
  }
  const matches = packaging.value === 'zip' ? isZipName : isTarGzName
  return names.every(matches) ? null : 'notAnArchive'
})
// CSV is the one tabular format that is plain text, so its header can be checked here. The check is
// asynchronous (a Blob read); a stale answer for an earlier selection is discarded.
const csvHeader = ref<string[] | null>(null)
watch(
  [files, sourceFormat],
  async ([selected, format]) => {
    csvHeader.value = null
    const [file] = selected
    if (format !== 'csv' || !file) return
    let header: string[]
    try {
      header = await readCsvHeader(file)
    } catch {
      return // unreadable here: leave the verdict to the server
    }
    if (files.value[0] === file) csvHeader.value = header
  },
  { flush: 'post' },
)
const headerProblem = computed(
  () => csvHeader.value !== null && !isPersonRegisterHeader(csvHeader.value),
)
const foundColumns = computed(() => {
  const columns = csvHeader.value ?? []
  return columns.length > 8 ? `${columns.slice(0, 8).join(', ')}, …` : columns.join(', ')
})
const usesProfile = computed(() => sourceFormat.value !== 'tei')
const canSubmit = computed(
  () =>
    files.value.length > 0 &&
    sizeProblem.value === null &&
    packagingProblem.value === null &&
    !headerProblem.value,
)

const importMutation = useImportSnapshot()
const snapshotId = ref<string | null>(null)
const status = useSnapshotStatus(snapshotId)

function importErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'validation_error':
        return t('projects.import.errors.validation')
      case 'payload_too_large':
        return t('projects.import.errors.tooLarge')
      case 'network_error':
        return t('projects.import.errors.network')
    }
  }
  return t('projects.import.errors.generic')
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  try {
    const snapshot = await importMutation.mutateAsync({
      projectId: projectId.value,
      sourceFormat: sourceFormat.value,
      packaging: packaging.value,
      files: files.value,
    })
    snapshotId.value = snapshot.id
  } catch {
    // importMutation.isError/.error already reflect this; the form stays open to show it.
  }
}
</script>

<template>
  <main class="import-view">
    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('projects.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="import-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('projects.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <p v-if="project.isPending.value" role="status">{{ t('projects.loading') }}</p>
      <div v-else-if="project.isError.value" class="import-load-error">
        <p role="alert">{{ t('projects.overview.loadError') }}</p>
        <AppButton class="import-retry" type="button" @click="() => project.refetch()">
          {{ t('projects.retry') }}
        </AppButton>
      </div>
      <template v-else-if="project.data.value">
        <h1 class="import-title">
          {{ t('projects.import.title', { project: project.data.value.display_name }) }}
        </h1>

        <p v-if="!canImport" class="import-forbidden">{{ t('projects.import.forbidden') }}</p>
        <template v-else>
          <form v-if="!snapshotId" class="import-form" novalidate @submit.prevent="submit">
            <AppListbox
              v-model="sourceFormat"
              class="import-format"
              :label="t('projects.import.format')"
              :options="sourceFormatOptions"
            />
            <AppListbox
              v-if="isTei"
              v-model="packaging"
              class="import-packaging"
              :label="t('projects.import.packagingLabel')"
              :options="packagingOptions"
            />
            <div class="import-file-field">
              <label for="import-file">{{ t('projects.import.file') }}</label>
              <input
                id="import-file"
                :key="fileInputKey"
                type="file"
                required
                :multiple="packaging === 'loose'"
                :aria-describedby="usesProfile ? 'import-limits import-profile' : 'import-limits'"
                @change="onFileChange"
              />
            </div>
            <div v-if="usesProfile" id="import-profile" class="import-profile">
              <p>{{ t('projects.import.profile.intro') }}</p>
              <p class="import-profile-columns">
                <code v-for="column in PERSON_REGISTER_COLUMNS" :key="column">{{ column }}</code>
              </p>
              <p>{{ t('projects.import.profile.arrays') }}</p>
            </div>
            <div id="import-limits" class="import-limits">
              <template v-if="limits.data.value">
                <p class="import-limits-upload">
                  {{
                    t('projects.import.limits.upload', {
                      part: mebibytes(limits.data.value.max_upload_part_bytes),
                      total: mebibytes(limits.data.value.max_total_upload_bytes),
                    })
                  }}
                </p>
                <p v-if="isArchive || packaging === 'loose'" class="import-limits-archive">
                  {{
                    t('projects.import.limits.archive', {
                      members: n(limits.data.value.import_limits.max_member_count, 'integer'),
                      expanded: mebibytes(limits.data.value.import_limits.max_total_expanded_bytes),
                    })
                  }}
                </p>
              </template>
              <p v-else-if="limits.isError.value" class="import-limits-unknown">
                {{ t('projects.import.limits.unavailable') }}
              </p>
            </div>
            <p v-if="sizeProblem === 'part'" role="alert" class="import-error">
              {{ t('projects.import.errors.partTooLarge') }}
            </p>
            <p v-else-if="sizeProblem === 'total'" role="alert" class="import-error">
              {{ t('projects.import.errors.totalTooLarge') }}
            </p>
            <p v-if="packagingProblem === 'looksLikeArchive'" role="alert" class="import-error">
              {{ t('projects.import.errors.looksLikeArchive') }}
            </p>
            <p v-else-if="packagingProblem === 'notAnArchive'" role="alert" class="import-error">
              {{ t('projects.import.errors.notAnArchive') }}
            </p>
            <p v-if="headerProblem" role="alert" class="import-error">
              {{
                t('projects.import.errors.headerMismatch', {
                  expected: PERSON_REGISTER_COLUMNS.join(', '),
                  found: foundColumns,
                })
              }}
            </p>
            <p v-if="importMutation.isError.value" role="alert" class="import-error">
              {{ importErrorMessage(importMutation.error.value) }}
            </p>
            <AppButton
              class="import-submit"
              type="submit"
              :disabled="!canSubmit || importMutation.isPending.value"
            >
              {{
                importMutation.isPending.value
                  ? t('projects.import.submitting')
                  : t('projects.import.submit')
              }}
            </AppButton>
          </form>

          <div v-else class="import-status">
            <p v-if="status.isPending.value" role="status">
              {{ t('projects.import.status.pending') }}
            </p>
            <div v-else-if="status.isError.value" class="import-load-error">
              <p role="alert">{{ t('projects.import.status.pollError') }}</p>
              <AppButton class="import-retry" type="button" @click="() => status.refetch()">
                {{ t('projects.retry') }}
              </AppButton>
            </div>
            <template v-else-if="status.data.value">
              <div v-if="status.data.value.status === 'ready'" class="import-status-ready">
                <p>
                  {{
                    t('projects.import.status.ready', {
                      count: status.data.value.record_count ?? 0,
                    })
                  }}
                </p>
                <p class="import-status-provenance">
                  <span class="import-status-provenance-label">{{
                    t('projects.snapshots.checksum')
                  }}</span>
                  <code>{{ status.data.value.source_sha256 }}</code>
                </p>
                <RouterLink
                  :to="{ name: 'projectOverview', params: { projectId } }"
                  class="import-status-overview-link"
                >
                  {{ t('projects.import.status.toOverview') }}
                </RouterLink>
              </div>
              <p
                v-else-if="status.data.value.status === 'failed'"
                role="alert"
                class="import-status-failed"
              >
                {{
                  status.data.value.failure_diagnostic ?? t('projects.import.status.failedGeneric')
                }}
              </p>
              <p v-else role="status">{{ t('projects.import.status.pending') }}</p>
            </template>
          </div>
        </template>
      </template>
    </template>
  </main>
</template>

<style scoped>
.import-view {
  flex: 1;
  width: 100%;
  max-width: 32rem;
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
}

.import-title {
  margin: 0 0 var(--space-6);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}

.import-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

.import-load-error p,
.import-error,
.import-status-failed {
  margin: 0;
  color: var(--critical);
}

.import-forbidden {
  color: var(--text-secondary);
}

.import-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

.import-format,
.import-profile {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.import-profile-columns {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.import-packaging {
  width: 14rem;
}

.import-limits {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.import-limits p {
  margin: 0;
}

.import-file-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--font-size-body-strong);
}

.import-status-ready {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  color: var(--good);
}

.import-status-ready p {
  margin: 0;
}

.import-status-provenance {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}

.import-status-overview-link {
  color: var(--accent);
  text-underline-offset: 0.2em;
}
</style>
