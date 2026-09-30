<script setup lang="ts">
// The full, unlisted history of a project's snapshots (decision, 2026-09-30): Übersicht shows the
// present one and imports new ones; this page is reached only through its link, never through the
// sidebar, and stays read-only.
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useSessionStore } from '@/stores/session'

import { hasProjectRole } from './projectRoles'
import SnapshotList from './SnapshotList.vue'
import { useProject } from './useProjects'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
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
const accessUnavailable = computed(() => {
  const error = query.error.value
  return (
    error instanceof ApiError && error.status !== null && [401, 403, 404].includes(error.status)
  )
})

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
  <main class="project-snapshots app-page-frame">
    <header class="project-snapshots-heading app-page-heading">
      <h1 class="app-page-heading__title">{{ t('data.title') }}</h1>
    </header>
    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="app-card"
      announcement="polite"
    >
      {{ t('data.loading') }}
    </AppFeedback>
    <AppFeedback
      v-else-if="session.status === 'error'"
      class="app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('projects.sessionLoadError') }}
      <template #actions
        ><AppButton variant="ghost" @click="session.initialize()">{{
          t('projects.retry')
        }}</AppButton></template
      >
    </AppFeedback>
    <template v-else-if="canUseData">
      <AppFeedback v-if="query.isPending.value" class="app-card" announcement="polite">{{
        t('data.loading')
      }}</AppFeedback>
      <AppFeedback
        v-else-if="query.isError.value"
        class="app-card"
        announcement="assertive"
        tone="critical"
      >
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
}
</style>
