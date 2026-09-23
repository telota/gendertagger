<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppListbox from '@/components/base/AppListbox.vue'
import { useSessionStore } from '@/stores/session'

import { useProject } from './useProjects'
import { useImportSnapshot, useSnapshotStatus, type SourceFormat } from './useSnapshotImport'

const { t } = useI18n()
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

const project = useProject(projectId)
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
const file = ref<File | null>(null)

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  file.value = input.files?.[0] ?? null
}

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
  if (!file.value) return
  try {
    const snapshot = await importMutation.mutateAsync({
      projectId: projectId.value,
      sourceFormat: sourceFormat.value,
      file: file.value,
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
            <div class="import-file-field">
              <label for="import-file">{{ t('projects.import.file') }}</label>
              <input id="import-file" type="file" required @change="onFileChange" />
            </div>
            <p v-if="importMutation.isError.value" role="alert" class="import-error">
              {{ importErrorMessage(importMutation.error.value) }}
            </p>
            <AppButton
              class="import-submit"
              type="submit"
              :disabled="!file || importMutation.isPending.value"
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
              <p v-if="status.data.value.status === 'ready'" class="import-status-ready">
                {{
                  t('projects.import.status.ready', { count: status.data.value.record_count ?? 0 })
                }}
              </p>
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

.import-format {
  width: 12rem;
}

.import-file-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--font-size-body-strong);
}

.import-status-ready {
  color: var(--good);
}
</style>
