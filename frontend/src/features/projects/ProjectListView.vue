<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useSessionStore } from '@/stores/session'
import ProjectCreationForm from './ProjectCreationForm.vue'

import { useProjectList } from './useProjects'
import { useManagedProjects } from './useManagedProjects'
import { useRoleLabel } from './useRoleLabel'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()

// Wait for the one loading -> ready transition before deciding, exactly like /change-password:
// session.initialize() is still pending on every fresh page load, cookie or not. A genuine
// session.status === 'error' (the server itself, not the visitor) is handled below, not here.
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

const query = useProjectList(isSignedIn)
const projects = computed(() => query.data.value?.pages.flatMap((page) => page.items) ?? [])
const managedQuery = useManagedProjects(
  isSignedIn,
  computed(() => session.user?.id ?? null),
)
const managedProjects = computed(
  () => managedQuery.data.value?.pages.flatMap((page) => page.items) ?? [],
)

const roleLabel = useRoleLabel()

const canCreateProject = computed(
  () =>
    session.user?.roles.includes('operator') === true ||
    session.user?.roles.includes('admin') === true,
)

function openCreatedProject(projectId: string): void {
  void router.push({ name: 'projectOverview', params: { projectId } })
}

function loadMore(): void {
  void query.fetchNextPage()
}
</script>

<template>
  <main class="project-list">
    <h1 class="project-list-title">{{ t('projects.title') }}</h1>

    <AppFeedback
      v-if="session.status === 'idle' || session.status === 'loading'"
      announcement="polite"
    >
      {{ t('projects.loading') }}
    </AppFeedback>
    <AppFeedback v-else-if="session.status === 'error'" announcement="assertive" tone="critical">
      {{ t('projects.sessionLoadError') }}
      <template #actions>
        <AppButton type="button" @click="retrySession">{{ t('projects.retry') }}</AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <ProjectCreationForm
        v-if="canCreateProject && session.user"
        :principal-id="session.user.id"
        :is-administrator="session.user.roles.includes('admin')"
        @created="openCreatedProject"
      />
      <section v-if="managedProjects.length" class="project-list-managed">
        <h2>{{ t('projectMembers.managedProjects') }}</h2>
        <ul class="project-list-items">
          <li v-for="project in managedProjects" :key="project.id" class="project-card">
            <RouterLink :to="{ name: 'projectMembers', params: { projectId: project.id } }">
              {{ project.display_name }}
            </RouterLink>
          </li>
        </ul>
      </section>
      <AppFeedback v-if="query.isPending.value" announcement="polite">{{
        t('projects.loading')
      }}</AppFeedback>
      <AppFeedback v-else-if="query.isError.value" announcement="assertive" tone="critical">
        {{ t('projects.loadError') }}
        <template #actions>
          <AppButton class="project-list-retry" type="button" @click="() => query.refetch()">
            {{ t('projects.retry') }}
          </AppButton>
        </template>
      </AppFeedback>
      <template v-else>
        <p v-if="projects.length === 0" class="project-list-empty">{{ t('projects.empty') }}</p>
        <ul v-else class="project-list-items">
          <li v-for="project in projects" :key="project.id" class="project-card">
            <h2 class="project-card-title">
              <RouterLink
                :to="{ name: 'projectOverview', params: { projectId: project.id } }"
                class="project-card-link"
              >
                {{ project.display_name }}
              </RouterLink>
            </h2>
            <p v-if="project.description" class="project-card-description">
              {{ project.description }}
            </p>
            <span class="project-card-role">{{ roleLabel(project.current_user_role) }}</span>
          </li>
        </ul>
        <AppButton
          v-if="query.hasNextPage.value"
          class="project-list-load-more"
          type="button"
          @click="loadMore"
        >
          {{ t('projects.loadMore') }}
        </AppButton>
      </template>
    </template>
  </main>
</template>

<style scoped>
.project-list {
  flex: 1;
  width: 100%;
  max-width: 48rem;
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
}

.project-list-title {
  margin: 0 0 var(--space-6);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}

.project-list-empty {
  color: var(--text-secondary);
}

.project-list-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin: var(--space-6) 0;
  padding: 0;
  list-style: none;
}

.project-card {
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.project-card-title {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.project-card-link {
  color: inherit;
  text-decoration: none;
}

.project-card-link:hover {
  text-decoration: underline;
}

.project-card-description {
  margin: 0 0 var(--space-2);
  color: var(--text-secondary);
}

.project-card-role {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}
</style>
