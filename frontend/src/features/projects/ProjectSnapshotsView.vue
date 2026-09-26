<script setup lang="ts">
import { PhMinus, PhUploadSimple } from '@phosphor-icons/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useSessionStore } from '@/stores/session'

import { hasProjectRole } from './projectRoles'
import SnapshotImportForm from './SnapshotImportForm.vue'
import SnapshotList from './SnapshotList.vue'
import { useProject } from './useProjects'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const importOpen = ref(false)
const importMounted = ref(false)
const projectId = computed(() => {
  const raw = route.params.projectId
  return (Array.isArray(raw) ? raw[0] : raw) ?? ''
})
const canUseData = computed(() => session.canUsePrivateNavigation)
const query = useProject(projectId, canUseData)
const project = computed(() => {
  const value = query.data.value
  return canUseData.value &&
    query.isSuccess.value &&
    value?.id === projectId.value &&
    hasProjectRole(value.current_user_role, 'viewer')
    ? value
    : null
})
const hasImportRole = computed(() => {
  const value = query.data.value
  return (
    query.isSuccess.value &&
    value?.id === projectId.value &&
    hasProjectRole(value.current_user_role, 'operator')
  )
})
const canImport = computed(() => canUseData.value && hasImportRole.value)
const accessUnavailable = computed(() => {
  const error = query.error.value
  return (
    error instanceof ApiError && error.status !== null && [401, 403, 404].includes(error.status)
  )
})

function resetImport(): void {
  importOpen.value = false
  importMounted.value = false
}

function toggleImport(): void {
  importOpen.value = !importOpen.value
  if (importOpen.value) importMounted.value = true
}

watch([() => session.user?.id, projectId], resetImport)
watch(
  [accessUnavailable, () => query.isSuccess.value, hasImportRole],
  ([unavailable, success, allowed]) => {
    if (unavailable || (success && !allowed)) resetImport()
  },
)
watch(
  [() => session.status, () => session.mustChangePassword],
  ([status, mustChangePassword]) => {
    if (status !== 'ready') return
    if (!session.isSignedIn) {
      void router.replace({ name: 'login', query: { redirect: route.fullPath } })
    } else if (mustChangePassword) {
      void router.replace({ name: 'changePassword', query: { redirect: route.fullPath } })
    }
  },
  { immediate: true },
)
</script>

<template>
  <main class="project-snapshots">
    <div class="project-snapshots-heading">
      <h1>{{ t('data.title') }}</h1>
      <AppButton
        v-if="canImport"
        class="project-snapshots-import"
        variant="ghost"
        :aria-expanded="importOpen"
        aria-controls="project-import-panel"
        @click="toggleImport"
      >
        <PhMinus v-if="importOpen" :size="18" aria-hidden="true" />
        <PhUploadSimple v-else :size="18" aria-hidden="true" />
        {{ importOpen ? t('data.hideImport') : t('data.importAction') }}
      </AppButton>
    </div>
    <div
      v-show="importOpen && canImport"
      id="project-import-panel"
      class="project-snapshots-import-panel"
    >
      <SnapshotImportForm
        v-if="importMounted && session.user && project"
        :key="`${session.user.id}:${projectId}`"
        :project-id="project.id"
      />
    </div>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      announcement="polite"
    >
      {{ t('data.loading') }}
    </AppFeedback>
    <AppFeedback v-else-if="session.status === 'error'" announcement="assertive" tone="critical">
      {{ t('projects.sessionLoadError') }}
      <template #actions
        ><AppButton variant="ghost" @click="session.initialize()">{{
          t('projects.retry')
        }}</AppButton></template
      >
    </AppFeedback>
    <template v-else-if="canUseData">
      <AppFeedback v-if="query.isPending.value" announcement="polite">{{
        t('data.loading')
      }}</AppFeedback>
      <AppFeedback v-else-if="query.isError.value" announcement="assertive" tone="critical">
        {{ accessUnavailable ? t('data.accessUnavailable') : t('data.projectLoadError') }}
        <template #actions>
          <AppButton v-if="accessUnavailable" :to="{ name: 'projects' }" variant="ghost">{{
            t('projects.title')
          }}</AppButton>
          <AppButton
            v-else
            class="project-snapshots-retry"
            variant="ghost"
            :disabled="query.isFetching.value"
            @click="() => query.refetch()"
            >{{ t('projects.retry') }}</AppButton
          >
        </template>
      </AppFeedback>
      <SnapshotList
        v-else-if="project"
        :key="`${session.user?.id}:${project.id}`"
        :project-id="project.id"
      />
    </template>
  </main>
</template>

<style scoped>
.project-snapshots {
  container: snapshot-index / inline-size;
  flex: 1;
  min-inline-size: 0;
  inline-size: 100%;
  max-inline-size: 60rem;
  margin-inline: auto;
  padding: var(--space-8) var(--page-gutter);
}
.project-snapshots-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3) var(--space-6);
  margin-block-end: var(--space-6);
}
.project-snapshots h1 {
  margin: 0;
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}
.project-snapshots-import svg {
  flex-shrink: 0;
}
.project-snapshots-import-panel {
  margin-block-end: var(--space-8);
}
</style>
