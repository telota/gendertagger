<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useSessionStore } from '@/stores/session'

import ProjectGameModeSetting from './ProjectGameModeSetting.vue'
import ProjectDataStats from './ProjectDataStats.vue'
import ProjectOverviewSection from './ProjectOverviewSection.vue'
import ProjectReviewStats from './ProjectReviewStats.vue'
import { useProject } from './useProjects'
import { useRoleLabel } from './useRoleLabel'

const { t, d } = useI18n()
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
  <main class="project-overview app-page-frame">
    <header class="project-overview-heading app-page-heading">
      <h1 class="project-overview-title app-page-heading__title">
        {{ query.data.value?.display_name ?? t('nav.overview') }}
      </h1>
    </header>

    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      class="app-card"
      announcement="polite"
    >
      {{ t('projects.loading') }}
    </AppFeedback>
    <AppFeedback
      v-else-if="session.status === 'error'"
      class="project-overview-load-error app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('projects.sessionLoadError') }}
      <template #actions>
        <AppButton type="button" variant="ghost" @click="retrySession">{{
          t('projects.retry')
        }}</AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <AppFeedback v-if="query.isPending.value" class="app-card" announcement="polite">
        {{ t('projects.loading') }}
      </AppFeedback>
      <AppFeedback
        v-else-if="query.isError.value"
        class="project-overview-load-error app-card"
        announcement="assertive"
        tone="critical"
      >
        {{ t('projects.overview.loadError') }}
        <template #actions>
          <AppButton type="button" variant="ghost" @click="() => query.refetch()">{{
            t('projects.retry')
          }}</AppButton>
        </template>
      </AppFeedback>
      <template v-else-if="query.data.value">
        <div class="project-overview-card app-card app-card--sectioned">
          <ProjectOverviewSection>
            <dl class="project-overview-facts">
              <div class="project-overview-fact">
                <dt>{{ t('projects.overview.slug') }}</dt>
                <dd>{{ query.data.value.slug }}</dd>
              </div>
              <div class="project-overview-fact">
                <dt>{{ t('projects.overview.role') }}</dt>
                <dd>{{ roleLabel(query.data.value.current_user_role) }}</dd>
              </div>
              <div class="project-overview-fact">
                <dt>{{ t('projects.overview.team') }}</dt>
                <dd>{{ query.data.value.team.display_name }}</dd>
              </div>
              <div class="project-overview-fact">
                <dt>{{ t('projects.overview.created') }}</dt>
                <dd>{{ d(new Date(query.data.value.created_at), 'date') }}</dd>
              </div>
            </dl>
            <p v-if="query.data.value.description" class="project-overview-description">
              {{ query.data.value.description }}
            </p>
            <p v-else class="project-overview-no-description">
              {{ t('projects.overview.noDescription') }}
            </p>
          </ProjectOverviewSection>
          <ProjectDataStats :project-id="projectId" />
          <ProjectReviewStats
            :project-id="projectId"
            :aggregation-id="query.data.value.working_aggregation_execution_id ?? null"
          />
          <ProjectGameModeSetting
            v-if="query.data.value.current_user_role === 'operator'"
            :project-id="projectId"
            :enabled="query.data.value.game_mode_enabled === true"
          />
        </div>
      </template>
    </template>
  </main>
</template>

<style scoped>
.project-overview {
  container: project-overview / inline-size;
}

/* Four facts: one column, two, or all four in a row — never three and an orphan. Side by side, a
   long value (a team name) would wrap under its label while the short ones did not, so in columns
   every label sits above its value, like the figures below. */
.project-overview-facts {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-2) var(--space-6);
  margin: 0 0 var(--space-4);
}
@container project-overview (min-width: 30rem) {
  .project-overview-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4) var(--space-6);
  }
  .project-overview-fact {
    flex-direction: column;
  }
  .project-overview-fact dt {
    font-size: var(--font-size-small);
  }
}
@container project-overview (min-width: 52rem) {
  .project-overview-facts {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.project-overview-fact {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-2);
  min-inline-size: 0;
  font-size: var(--font-size-body);
}

.project-overview-fact dt {
  color: var(--text-secondary);
}

.project-overview-fact dd {
  min-inline-size: 0;
  margin: 0;
}

.project-overview-description {
  margin: 0;
  max-inline-size: 65ch;
}

.project-overview-no-description {
  margin: 0;
  color: var(--text-secondary);
}
</style>
