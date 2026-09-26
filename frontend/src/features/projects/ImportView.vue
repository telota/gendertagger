<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useSessionStore } from '@/stores/session'

import { hasProjectRole } from './projectRoles'
import SnapshotImportForm from './SnapshotImportForm.vue'
import { useProject } from './useProjects'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const formMounted = ref(false)
const projectId = computed(() => {
  const raw = route.params.projectId
  return (Array.isArray(raw) ? raw[0] : raw) ?? ''
})
const canUseImport = computed(() => session.canUsePrivateNavigation)
const query = useProject(projectId, canUseImport)
const project = computed(() => {
  const value = query.data.value
  return query.isSuccess.value && value?.id === projectId.value ? value : null
})
const hasImportRole = computed(() => hasProjectRole(project.value?.current_user_role, 'operator'))
const canImport = computed(() => canUseImport.value && hasImportRole.value)
const accessUnavailable = computed(() => {
  const error = query.error.value
  return (
    error instanceof ApiError && error.status !== null && [401, 403, 404].includes(error.status)
  )
})

watch(
  canImport,
  (allowed) => {
    if (allowed) formMounted.value = true
  },
  { immediate: true },
)
watch([() => session.user?.id, projectId], () => {
  formMounted.value = false
})
watch(
  [accessUnavailable, () => query.isSuccess.value, hasImportRole],
  ([unavailable, success, allowed]) => {
    if (unavailable || (success && !allowed)) formMounted.value = false
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
  <main class="import-view">
    <h1 class="import-view-title">
      {{
        project ? t('projects.import.title', { project: project.display_name }) : t('nav.import')
      }}
    </h1>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      announcement="polite"
    >
      {{ t('projects.loading') }}
    </AppFeedback>
    <AppFeedback v-else-if="session.status === 'error'" announcement="assertive" tone="critical">
      {{ t('projects.sessionLoadError') }}
      <template #actions>
        <AppButton variant="ghost" @click="session.initialize()">{{
          t('projects.retry')
        }}</AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="canUseImport">
      <AppFeedback v-if="query.isPending.value" announcement="polite">{{
        t('projects.loading')
      }}</AppFeedback>
      <AppFeedback v-else-if="query.isError.value" announcement="assertive" tone="critical">
        {{ accessUnavailable ? t('data.accessUnavailable') : t('projects.overview.loadError') }}
        <template #actions>
          <AppButton v-if="accessUnavailable" :to="{ name: 'projects' }" variant="ghost">{{
            t('projects.title')
          }}</AppButton>
          <AppButton
            v-else
            variant="ghost"
            :disabled="query.isFetching.value"
            @click="query.refetch()"
          >
            {{ t('projects.retry') }}
          </AppButton>
        </template>
      </AppFeedback>
      <p v-else-if="project && !hasImportRole" class="import-view-forbidden">
        {{ t('projects.import.forbidden') }}
      </p>
    </template>
    <div v-show="canImport" class="import-view-form">
      <SnapshotImportForm
        v-if="formMounted && session.user && project"
        :key="`${session.user.id}:${project.id}`"
        :project-id="project.id"
      />
    </div>
  </main>
</template>

<style scoped>
.import-view {
  flex: 1;
  min-inline-size: 0;
  inline-size: 100%;
  max-inline-size: 60rem;
  margin-inline: auto;
  padding: var(--space-8) var(--page-gutter);
}

.import-view-title {
  margin: 0 0 var(--space-6);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
  overflow-wrap: anywhere;
}

.import-view-forbidden {
  margin: 0;
  color: var(--text-secondary);
}
</style>
