<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import { useSessionStore } from '@/stores/session'

import SnapshotList from './SnapshotList.vue'
import { useProject } from './useProjects'
import { useRoleLabel } from './useRoleLabel'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const roleLabel = useRoleLabel()

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

const query = useProject(projectId, isSignedIn)
</script>

<template>
  <main class="project-overview">
    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('projects.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="project-overview-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('projects.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <p v-if="query.isPending.value" role="status">{{ t('projects.loading') }}</p>
      <div v-else-if="query.isError.value" class="project-overview-load-error">
        <p role="alert">{{ t('projects.overview.loadError') }}</p>
        <AppButton type="button" @click="() => query.refetch()">{{
          t('projects.retry')
        }}</AppButton>
      </div>
      <template v-else-if="query.data.value">
        <h1 class="project-overview-title">{{ query.data.value.display_name }}</h1>
        <dl class="project-overview-facts">
          <div class="project-overview-fact">
            <dt>{{ t('projects.overview.slug') }}</dt>
            <dd>{{ query.data.value.slug }}</dd>
          </div>
          <div class="project-overview-fact">
            <dt>{{ t('projects.overview.role') }}</dt>
            <dd>{{ roleLabel(query.data.value.current_user_role) }}</dd>
          </div>
        </dl>
        <p v-if="query.data.value.description" class="project-overview-description">
          {{ query.data.value.description }}
        </p>
        <p v-else class="project-overview-no-description">
          {{ t('projects.overview.noDescription') }}
        </p>
        <RouterLink
          :to="{ name: 'projectImport', params: { projectId } }"
          class="project-overview-import-link"
        >
          {{ t('projects.overview.importAction') }}
        </RouterLink>
        <SnapshotList :project-id="projectId" />
      </template>
    </template>
  </main>
</template>

<style scoped>
.project-overview {
  flex: 1;
  width: 100%;
  max-width: 40rem;
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
}

.project-overview-title {
  margin: 0 0 var(--space-4);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}

.project-overview-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

.project-overview-load-error p {
  margin: 0;
  color: var(--critical);
}

.project-overview-facts {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0 0 var(--space-4);
}

.project-overview-fact {
  display: flex;
  gap: var(--space-2);
  font-size: var(--font-size-body);
}

.project-overview-fact dt {
  color: var(--text-secondary);
}

.project-overview-fact dd {
  margin: 0;
}

.project-overview-description {
  margin: 0 0 var(--space-6);
}

.project-overview-no-description {
  margin: 0 0 var(--space-6);
  color: var(--text-secondary);
}

.project-overview-import-link {
  color: var(--accent);
  text-underline-offset: 0.2em;
}
</style>
