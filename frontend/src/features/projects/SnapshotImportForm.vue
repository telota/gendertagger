<script setup lang="ts">
import { PhFile, PhUploadSimple, PhX } from '@phosphor-icons/vue'
import { computed, nextTick, ref, toRef, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import { useDraftRegistration } from '@/composables/useDraftNavigation'

import {
  isPersonRegisterHeader,
  PERSON_REGISTER_COLUMNS,
  readCsvHeader,
} from './personRegisterProfile'
import {
  useImportSnapshot,
  useSnapshotStatus,
  useSnapshotUploadLimits,
  type SourceFormat,
  type SourcePackaging,
} from './useSnapshotImport'

interface ImportMode {
  sourceFormat: SourceFormat
  packaging: SourcePackaging
}

const props = defineProps<{ projectId: string }>()
const { t, n } = useI18n()
const instanceId = useId()
const titleId = `${instanceId}-title`
const fileId = `${instanceId}-file`
const dropHintId = `${instanceId}-drop-hint`
const limitsId = `${instanceId}-limits`
const profileId = `${instanceId}-profile`
const selectionErrorId = `${instanceId}-selection-error`
const selectedFilesTitleId = `${instanceId}-selected-files`
const csvValidationId = `${instanceId}-csv-validation`
const formElement = ref<HTMLFormElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const fileSelection = ref<HTMLElement | null>(null)
const statusHeading = ref<HTMLElement | null>(null)

const supportedFileTypes = [
  '.xml',
  '.tei',
  '.csv',
  '.xlsx',
  '.json',
  '.zip',
  '.tar.gz',
  '.tgz',
].join(',')

const sourceFormat = ref<SourceFormat | null>(null)
const packaging = ref<SourcePackaging | null>(null)
const files = ref<File[]>([])
const selectionError = ref<string | null>(null)
const csvHeader = ref<string[] | null>(null)
const csvHeaderPending = ref(false)
let csvValidationGeneration = 0
let draftGeneration = 0
// Remounting is the reliable way to clear a native file input and lets the same file be chosen again.
const fileInputKey = ref(0)
const isDragActive = ref(false)
let dragDepth = 0

const lowerName = (file: File): string => file.name.toLowerCase()
const isXmlFile = (file: File): boolean => /\.(xml|tei)$/.test(lowerName(file))
const isLooseXmlFile = (file: File): boolean => lowerName(file).endsWith('.xml')

function inferImportMode(selected: readonly File[]): ImportMode | null {
  if (selected.length === 0) return null
  if (selected.length > 1) {
    return selected.every(isLooseXmlFile) ? { sourceFormat: 'tei', packaging: 'loose' } : null
  }

  const [file] = selected
  if (!file) return null
  const name = lowerName(file)
  if (name.endsWith('.tar.gz') || name.endsWith('.tgz')) {
    return { sourceFormat: 'tei', packaging: 'tar_gz' }
  }
  if (name.endsWith('.zip')) return { sourceFormat: 'tei', packaging: 'zip' }
  if (isXmlFile(file)) return { sourceFormat: 'tei', packaging: 'single' }
  if (name.endsWith('.csv')) return { sourceFormat: 'csv', packaging: 'single' }
  if (name.endsWith('.xlsx')) return { sourceFormat: 'xlsx', packaging: 'single' }
  if (name.endsWith('.json')) return { sourceFormat: 'json', packaging: 'single' }
  return null
}

const importMutation = useImportSnapshot()

function applyFiles(selected: File[]): boolean {
  if (selected.length === 0 || importMutation.isPending.value) return false
  const mode = inferImportMode(selected)
  if (!mode) {
    selectionError.value = t('projects.import.errors.unsupportedSelection')
    fileInputKey.value += 1
    return false
  }

  files.value = selected
  sourceFormat.value = mode.sourceFormat
  packaging.value = mode.packaging
  selectionError.value = null
  csvHeader.value = null
  csvHeaderPending.value = mode.sourceFormat === 'csv'
  importMutation.reset()
  fileInputKey.value += 1
  return true
}

function acceptFiles(selected: File[]): boolean {
  if (selected.length === 0 || importMutation.isPending.value) return false
  return applyFiles([...files.value, ...selected])
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  acceptFiles(Array.from(input.files ?? []))
}

function browseFiles(): void {
  if (!importMutation.isPending.value) fileInput.value?.click()
}

function onDragEnter(): void {
  if (importMutation.isPending.value) return
  dragDepth += 1
  isDragActive.value = true
}

function onDragOver(): void {
  if (!importMutation.isPending.value) isDragActive.value = true
}

function onDragLeave(): void {
  if (importMutation.isPending.value) return
  dragDepth = Math.max(0, dragDepth - 1)
  isDragActive.value = dragDepth > 0
}

function onDrop(event: DragEvent): void {
  dragDepth = 0
  isDragActive.value = false
  if (importMutation.isPending.value) return
  acceptFiles(Array.from(event.dataTransfer?.files ?? []))
}

function focusBrowseButton(): void {
  formElement.value?.querySelector<HTMLButtonElement>('.import-browse')?.focus()
}

async function clearFiles(focusBrowse = false): Promise<void> {
  if (importMutation.isPending.value) return
  draftGeneration += 1
  files.value = []
  sourceFormat.value = null
  packaging.value = null
  selectionError.value = null
  csvHeader.value = null
  csvHeaderPending.value = false
  fileInputKey.value += 1
  importMutation.reset()
  if (focusBrowse) {
    await nextTick()
    focusBrowseButton()
  }
}

async function removeFile(index: number): Promise<void> {
  if (importMutation.isPending.value) return
  const remaining = files.value.filter((_, fileIndex) => fileIndex !== index)
  if (remaining.length === 0) {
    await clearFiles(true)
    return
  }
  applyFiles(remaining)
  await nextTick()
  const removeButtons =
    fileSelection.value?.querySelectorAll<HTMLButtonElement>('.import-file-remove') ?? []
  removeButtons[Math.min(index, removeButtons.length - 1)]?.focus()
}

const isArchive = computed(() => packaging.value === 'zip' || packaging.value === 'tar_gz')
const usesTabularProfile = computed(
  () => sourceFormat.value === 'csv' || sourceFormat.value === 'xlsx',
)
const usesJsonProfile = computed(() => sourceFormat.value === 'json')
const usesProfile = computed(() => usesTabularProfile.value || usesJsonProfile.value)
const sourceFormatLabel = computed(() => {
  switch (sourceFormat.value) {
    case 'tei':
      return 'TEI XML'
    case 'csv':
      return 'CSV'
    case 'xlsx':
      return 'XLSX'
    case 'json':
      return 'JSON'
    default:
      return ''
  }
})
const packagingLabel = computed(() => {
  switch (packaging.value) {
    case 'single':
      return t('projects.import.packaging.single')
    case 'loose':
      return t('projects.import.packaging.loose')
    case 'zip':
      return t('projects.import.packaging.zip')
    case 'tar_gz':
      return t('projects.import.packaging.tarGz')
    default:
      return ''
  }
})

const limits = useSnapshotUploadLimits()
const mebibytes = (bytes: number): string => n(bytes / (1024 * 1024), 'decimal')
const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${n(bytes, 'integer')} B`
  if (bytes < 1024 * 1024) return `${n(bytes / 1024, 'decimal')} KiB`
  return `${mebibytes(bytes)} MiB`
}
const totalFileSize = computed(() =>
  formatFileSize(files.value.reduce((sum, file) => sum + file.size, 0)),
)
const selectionAnnouncement = computed(() => {
  if (files.value.length === 0) return ''
  return `${t('projects.import.upload.selectedSummary', {
    count: n(files.value.length, 'integer'),
    size: totalFileSize.value,
  })}. ${t('projects.import.upload.importSettings')}: ${t('projects.import.upload.settingSummary', {
    format: sourceFormatLabel.value,
    delivery: packagingLabel.value,
  })}.`
})

// The bounds are the server's to enforce (a 413 is still handled below); checking them first only
// saves a doomed upload and lets the message name the problem rather than just the request.
const sizeProblem = computed<'part' | 'total' | null>(() => {
  const bounds = limits.data.value
  if (!bounds) return null
  if (files.value.some((file) => file.size > bounds.max_upload_part_bytes)) return 'part'
  const total = files.value.reduce((sum, file) => sum + file.size, 0)
  return total > bounds.max_total_upload_bytes ? 'total' : null
})
const memberCountProblem = computed(() => {
  const bounds = limits.data.value
  return (
    packaging.value === 'loose' &&
    bounds !== undefined &&
    files.value.length > bounds.import_limits.max_member_count
  )
})
const emptyFileNames = computed(() =>
  files.value
    .filter((file) => file.size === 0)
    .map((file) => file.name)
    .join(', '),
)
const duplicateFileNames = computed(() => {
  const seen = new Set<string>()
  const duplicateNames = new Set<string>()
  for (const file of files.value) {
    const normalized = file.name.normalize('NFC').toLowerCase()
    if (seen.has(normalized)) duplicateNames.add(file.name)
    seen.add(normalized)
  }
  return Array.from(duplicateNames).join(', ')
})

// CSV is the one tabular format that is plain text, so its header can be checked here. The check is
// asynchronous (a Blob read); a stale answer for an earlier selection is discarded.
watch(
  [files, sourceFormat],
  async ([selected, format]) => {
    const generation = ++csvValidationGeneration
    csvHeader.value = null
    const [file] = selected
    if (format !== 'csv' || !file) {
      csvHeaderPending.value = false
      return
    }
    csvHeaderPending.value = true
    let header: string[]
    try {
      header = await readCsvHeader(file)
    } catch {
      if (generation === csvValidationGeneration && files.value[0] === file) {
        csvHeaderPending.value = false
      }
      return // unreadable here: leave the verdict to the server
    }
    if (generation === csvValidationGeneration && files.value[0] === file) {
      csvHeader.value = header
      csvHeaderPending.value = false
    }
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
const canSubmit = computed(
  () =>
    files.value.length > 0 &&
    sourceFormat.value !== null &&
    packaging.value !== null &&
    sizeProblem.value === null &&
    !memberCountProblem.value &&
    emptyFileNames.value === '' &&
    duplicateFileNames.value === '' &&
    !csvHeaderPending.value &&
    !headerProblem.value,
)
const fileDescriptionIds = computed(() =>
  [
    dropHintId,
    limitsId,
    usesProfile.value ? profileId : null,
    csvHeaderPending.value ? csvValidationId : null,
    selectionError.value ? selectionErrorId : null,
  ]
    .filter(Boolean)
    .join(' '),
)

const snapshotId = ref<string | null>(null)
const status = useSnapshotStatus(snapshotId, toRef(props, 'projectId'))
const currentStatus = computed(() => {
  const value = status.data.value
  return value?.id === snapshotId.value && value.project_id === props.projectId ? value : null
})
const completedImportAnnouncement = computed(() => {
  const value = currentStatus.value
  if (value?.status !== 'ready') return ''
  return value.record_count === null
    ? t('projects.import.status.readyWithoutCount')
    : t('projects.import.status.ready', { count: value.record_count })
})

useDraftRegistration(
  () => snapshotId.value === null && files.value.length > 0,
  () => {
    draftGeneration += 1
    files.value = []
    fileInputKey.value += 1
    sourceFormat.value = null
    packaging.value = null
    selectionError.value = null
    csvHeader.value = null
    csvHeaderPending.value = false
    snapshotId.value = null
    importMutation.reset()
  },
)

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
  const format = sourceFormat.value
  const sourcePackaging = packaging.value
  if (!canSubmit.value || !format || !sourcePackaging || importMutation.isPending.value) return
  const generation = draftGeneration
  try {
    const snapshot = await importMutation.mutateAsync({
      projectId: props.projectId,
      sourceFormat: format,
      packaging: sourcePackaging,
      files: files.value,
    })
    if (generation !== draftGeneration) return
    snapshotId.value = snapshot.id
    await nextTick()
    statusHeading.value?.focus()
  } catch {
    // importMutation.isError/.error already reflect this; the form stays open to show it.
  }
}

async function resetImport(): Promise<void> {
  draftGeneration += 1
  files.value = []
  fileInputKey.value += 1
  sourceFormat.value = null
  packaging.value = null
  selectionError.value = null
  csvHeader.value = null
  csvHeaderPending.value = false
  snapshotId.value = null
  importMutation.reset()
  await nextTick()
  focusBrowseButton()
}
</script>

<template>
  <section class="snapshot-import-form" :aria-labelledby="titleId">
    <h2 :id="titleId" class="import-title">{{ t('projects.import.formTitle') }}</h2>
    <p
      class="import-visually-hidden import-completion-announcement"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      {{ completedImportAnnouncement }}
    </p>
    <form
      v-if="!snapshotId"
      ref="formElement"
      class="import-form"
      novalidate
      :aria-busy="importMutation.isPending.value || undefined"
      @submit.prevent="submit"
    >
      <p
        class="import-visually-hidden import-queue-announcement"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {{ selectionAnnouncement }}
      </p>
      <!-- Drag-and-drop is progressive enhancement; the real button below is its keyboard and
      touch equivalent. This region therefore deliberately has no synthetic keyboard handler. -->
      <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
      <div
        class="import-dropzone"
        :class="{
          'import-dropzone--active': isDragActive,
          'import-dropzone--selected': files.length > 0,
          'import-dropzone--disabled': importMutation.isPending.value,
        }"
        :aria-disabled="importMutation.isPending.value || undefined"
        :aria-describedby="fileDescriptionIds"
        :aria-label="t('projects.import.upload.dropzoneLabel')"
        role="group"
        @dragenter.prevent="onDragEnter"
        @dragover.prevent="onDragOver"
        @dragleave.prevent="onDragLeave"
        @drop.prevent="onDrop"
      >
        <input
          :id="fileId"
          :key="fileInputKey"
          ref="fileInput"
          class="import-file-input"
          type="file"
          :accept="supportedFileTypes"
          :aria-label="t('projects.import.file')"
          :aria-describedby="fileDescriptionIds"
          :disabled="importMutation.isPending.value"
          tabindex="-1"
          multiple
          @change="onFileChange"
        />
        <PhUploadSimple :size="32" aria-hidden="true" class="import-dropzone-icon" />
        <div class="import-dropzone-copy">
          <p class="import-dropzone-title">
            {{
              isDragActive
                ? t('projects.import.upload.dropActive')
                : t('projects.import.upload.dropTitle')
            }}
          </p>
          <p :id="dropHintId" class="import-dropzone-hint">
            {{ t('projects.import.upload.dropHint') }}
          </p>
        </div>
        <AppButton
          class="import-browse"
          type="button"
          variant="ghost"
          :disabled="importMutation.isPending.value"
          @click="browseFiles"
        >
          {{ t('projects.import.upload.browse') }}
        </AppButton>
        <p class="import-supported-types">{{ t('projects.import.upload.supported') }}</p>
      </div>

      <p
        v-if="selectionError"
        :id="selectionErrorId"
        role="alert"
        class="import-error import-selection-error"
      >
        {{ selectionError }}
      </p>

      <section
        v-if="files.length > 0"
        ref="fileSelection"
        class="import-file-selection"
        :aria-labelledby="selectedFilesTitleId"
      >
        <div class="import-file-selection-header">
          <div>
            <h3 :id="selectedFilesTitleId">{{ t('projects.import.upload.selectedFiles') }}</h3>
            <p class="import-file-total">
              {{
                t('projects.import.upload.selectedSummary', {
                  count: n(files.length, 'integer'),
                  size: totalFileSize,
                })
              }}
            </p>
          </div>
          <AppButton
            class="import-files-clear"
            type="button"
            variant="text"
            :disabled="importMutation.isPending.value"
            @click="clearFiles(true)"
          >
            {{ t('projects.import.upload.clearAll') }}
          </AppButton>
        </div>
        <ul class="import-file-list">
          <li
            v-for="(file, index) in files"
            :key="`${file.name}:${file.size}:${index}`"
            class="import-file-item"
          >
            <PhFile :size="20" aria-hidden="true" class="import-file-icon" />
            <span class="import-file-details">
              <span class="import-file-name">{{ file.name }}</span>
              <span class="import-file-size">{{ formatFileSize(file.size) }}</span>
            </span>
            <button
              class="import-file-remove"
              type="button"
              :disabled="importMutation.isPending.value"
              :aria-label="t('projects.import.upload.removeFile', { name: file.name })"
              @click="removeFile(index)"
            >
              <PhX :size="18" aria-hidden="true" />
            </button>
          </li>
        </ul>
        <div class="import-detected-source">
          <span class="import-detected-label">{{
            t('projects.import.upload.importSettings')
          }}</span>
          <strong>{{
            t('projects.import.upload.settingSummary', {
              format: sourceFormatLabel,
              delivery: packagingLabel,
            })
          }}</strong>
        </div>
      </section>

      <p
        v-if="csvHeaderPending"
        :id="csvValidationId"
        role="status"
        class="import-validation-status"
      >
        {{ t('projects.import.upload.validatingCsv') }}
      </p>

      <details v-if="usesProfile" :id="profileId" class="import-profile">
        <summary>{{ t('projects.import.profile.requirements') }}</summary>
        <div class="import-profile-content">
          <p>
            {{
              usesJsonProfile
                ? t('projects.import.profile.jsonIntro')
                : t('projects.import.profile.tabularIntro')
            }}
          </p>
          <p class="import-profile-columns">
            <code v-for="column in PERSON_REGISTER_COLUMNS" :key="column">{{ column }}</code>
          </p>
          <p>{{ t('projects.import.profile.arrays') }}</p>
        </div>
      </details>

      <div :id="limitsId" class="import-limits">
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
      <p v-if="memberCountProblem" role="alert" class="import-error">
        {{
          t('projects.import.errors.tooManyFiles', {
            count: n(limits.data.value?.import_limits.max_member_count ?? 0, 'integer'),
          })
        }}
      </p>
      <p v-if="emptyFileNames" role="alert" class="import-error">
        {{ t('projects.import.errors.emptyFiles', { names: emptyFileNames }) }}
      </p>
      <p v-if="duplicateFileNames" role="alert" class="import-error">
        {{ t('projects.import.errors.duplicateFiles', { names: duplicateFileNames }) }}
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
      <h3 ref="statusHeading" class="import-status-title" tabindex="-1">
        {{ t('projects.import.status.title') }}
      </h3>
      <p v-if="status.isPending.value" role="status">
        {{ t('projects.import.status.pending') }}
      </p>
      <div v-else-if="status.isError.value" class="import-load-error">
        <p role="alert">{{ t('projects.import.status.pollError') }}</p>
        <AppButton class="import-retry" type="button" @click="() => status.refetch()">
          {{ t('projects.retry') }}
        </AppButton>
      </div>
      <template v-else-if="currentStatus">
        <div v-if="currentStatus.status === 'ready'" class="import-status-ready">
          <p>
            {{
              currentStatus.record_count === null
                ? t('projects.import.status.readyWithoutCount')
                : t('projects.import.status.ready', { count: currentStatus.record_count })
            }}
          </p>
          <p class="import-status-provenance">
            <span class="import-status-provenance-label">{{
              t('projects.snapshots.checksum')
            }}</span>
            <code>{{ currentStatus.source_sha256 }}</code>
          </p>
        </div>
        <p v-else-if="currentStatus.status === 'failed'" role="alert" class="import-status-failed">
          {{ currentStatus.failure_diagnostic ?? t('projects.import.status.failedGeneric') }}
        </p>
        <p v-else role="status">{{ t('projects.import.status.pending') }}</p>
        <div
          v-if="currentStatus.status === 'ready' || currentStatus.status === 'failed'"
          class="import-status-actions"
        >
          <RouterLink
            v-if="currentStatus.status === 'ready'"
            :to="{
              name: 'snapshotDetail',
              params: { projectId: props.projectId, snapshotId: currentStatus.id },
            }"
            class="import-status-data-link"
          >
            {{ t('data.viewImportedData') }}
          </RouterLink>
          <AppButton class="import-another" type="button" variant="ghost" @click="resetImport">
            {{ t('projects.import.status.importAnother') }}
          </AppButton>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.snapshot-import-form {
  container: snapshot-import / inline-size;
  display: flex;
  min-inline-size: 0;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-5) var(--page-gutter);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
  overflow-wrap: anywhere;
}

.import-title,
.import-status-title,
.snapshot-import-form p {
  margin: 0;
}

.import-title {
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-title);
}

.import-visually-hidden {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

.import-form {
  display: grid;
  min-inline-size: 0;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-3);
  align-items: start;
}

.import-dropzone {
  display: flex;
  min-block-size: 10rem;
  min-inline-size: 0;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-5);
  border: 1px dashed var(--border);
  border-radius: var(--radius-input);
  background: var(--surface-1);
  text-align: center;
  transition:
    background-color var(--motion-state) ease-out,
    border-color var(--motion-state) ease-out;
}

.import-dropzone--active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 8%, var(--panel));
}

.import-dropzone--selected {
  min-block-size: 8rem;
}

.import-dropzone--disabled {
  opacity: 0.65;
}

.import-file-input {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

.import-dropzone-icon {
  color: var(--accent);
}

.import-dropzone-copy {
  display: grid;
  gap: var(--space-1);
}

.import-dropzone-title {
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.import-dropzone-hint,
.import-supported-types,
.import-file-total,
.import-file-size,
.import-limits,
.import-profile,
.import-validation-status {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.import-browse {
  margin-block: var(--space-1);
}

.import-file-selection {
  display: grid;
  min-inline-size: 0;
  gap: var(--space-2);
}

.import-file-selection-header {
  display: flex;
  min-inline-size: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.import-file-selection h3 {
  margin: 0;
  font-size: var(--font-size-body-strong);
  line-height: var(--line-height-body-strong);
}

.import-file-list {
  margin: 0;
  padding: 0;
  list-style: none;
  border-block: 1px solid var(--border);
}

.import-file-list li {
  display: grid;
  min-inline-size: 0;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: var(--space-3);
  align-items: center;
  padding-block: var(--space-2);
}

.import-file-list li + li {
  border-block-start: 1px solid var(--border);
}

.import-file-icon {
  color: var(--text-secondary);
}

.import-file-details {
  display: flex;
  min-inline-size: 0;
  flex-direction: column;
}

.import-file-name {
  overflow-wrap: anywhere;
  font-weight: var(--weight-semibold);
}

.import-file-remove {
  display: inline-flex;
  min-inline-size: var(--control-min-size);
  min-block-size: var(--control-min-size);
  align-items: center;
  justify-content: center;
  padding: var(--space-1);
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.import-file-remove:hover:not(:disabled) {
  background: var(--surface-1);
  color: var(--critical-text);
}

.import-file-remove:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.import-detected-source {
  display: flex;
  min-inline-size: 0;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--surface-1);
}

.import-detected-label {
  color: var(--text-secondary);
}

.import-profile {
  max-inline-size: 65ch;
}

.import-profile summary {
  color: var(--text-primary);
  font-weight: var(--weight-semibold);
  cursor: pointer;
}

.import-profile-content {
  display: grid;
  gap: var(--space-2);
  padding-block-start: var(--space-2);
}

.import-profile-columns {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.import-limits {
  justify-self: end;
  max-inline-size: 65ch;
  text-align: end;
}

.import-limits p + p {
  margin-block-start: var(--space-1);
}

.import-error,
.import-status-failed {
  color: var(--critical-text);
}

.import-submit {
  justify-self: end;
  margin-block-start: var(--space-1);
}

.import-status,
.import-status-ready {
  display: flex;
  min-inline-size: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.import-status-title {
  margin-block-end: var(--space-2);
  padding: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.import-status-ready {
  gap: var(--space-2);
  color: var(--good);
}

.import-status-provenance {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}

.import-status-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.import-status-data-link {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

@container snapshot-import (max-width: 30rem) {
  .import-dropzone {
    align-items: stretch;
    min-block-size: auto;
    padding: var(--space-4);
    text-align: start;
  }

  .import-dropzone-icon {
    align-self: flex-start;
  }

  .import-file-selection-header {
    flex-direction: column;
  }

  .import-files-clear {
    align-self: flex-start;
  }
}
</style>
