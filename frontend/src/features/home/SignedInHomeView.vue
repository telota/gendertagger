<script setup lang="ts">
import { PhArrowRight } from '@phosphor-icons/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useProjectList } from '@/features/projects/useProjects'
import { useRoleLabel } from '@/features/projects/useRoleLabel'
import { useSessionStore } from '@/stores/session'

interface WorkspaceLink {
  key: string
  label: string
  to: RouteLocationRaw
}

const { t } = useI18n()
const session = useSessionStore()
const roleLabel = useRoleLabel()
const displayName = computed(() => session.user?.display_name ?? '')
const canUseProjects = computed(() => session.canUsePrivateNavigation)
const projectQuery = useProjectList(canUseProjects, 4)
const projects = computed(() => projectQuery.data.value?.pages.flatMap((page) => page.items) ?? [])
const canCreateProjects = computed(
  () =>
    session.user?.roles.includes('operator') === true ||
    session.user?.roles.includes('admin') === true,
)
const isAdministrator = computed(() => session.user?.roles.includes('admin') === true)
const accountAccess = computed(() => {
  if (isAdministrator.value) {
    return {
      label: t('home.signedIn.workspace.access.admin'),
      description: t('home.signedIn.workspace.access.adminDescription'),
    }
  }
  if (canCreateProjects.value) {
    return {
      label: t('home.signedIn.workspace.access.operator'),
      description: t('home.signedIn.workspace.access.operatorDescription'),
    }
  }
  return {
    label: t('home.signedIn.workspace.access.projectAccess'),
    description: t('home.signedIn.workspace.access.projectAccessDescription'),
  }
})
const workspaceLinks = computed<WorkspaceLink[]>(() => {
  const links: WorkspaceLink[] = [
    {
      key: 'personal-settings',
      label: t('home.signedIn.workspace.personalSettings'),
      to: { name: 'userSettings' },
    },
  ]
  if (canCreateProjects.value) {
    links.push({
      key: 'project-management',
      label: t('home.signedIn.workspace.projectManagement'),
      to: { name: 'projects' },
    })
  }
  if (isAdministrator.value) {
    links.push(
      {
        key: 'users',
        label: t('home.signedIn.workspace.users'),
        to: { name: 'adminUsers' },
      },
      {
        key: 'teams',
        label: t('home.signedIn.workspace.teams'),
        to: { name: 'adminTeams' },
      },
      {
        key: 'publication',
        label: t('home.signedIn.workspace.publicationDetails'),
        to: { name: 'adminSettings' },
      },
    )
  }
  return links
})

function retryProjects(): void {
  if (!projectQuery.isFetching.value) void projectQuery.refetch()
}
</script>

<template>
  <div class="home-dashboard">
    <header class="home-dashboard-header app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="home-dashboard-title app-page-heading__title">
          {{ t('home.signedIn.welcomeBack', { name: displayName }) }}
        </h1>
        <p class="home-dashboard-introduction app-page-heading__description">
          {{ t('home.signedIn.introduction') }}
        </p>
      </div>
    </header>

    <div class="home-dashboard-layout">
      <section aria-labelledby="home-projects-title">
        <div class="home-dashboard-section-heading">
          <div>
            <h2 id="home-projects-title">{{ t('home.signedIn.projects.title') }}</h2>
            <p>{{ t('home.signedIn.projects.description') }}</p>
          </div>
          <AppButton :to="{ name: 'projects' }" variant="ghost">
            {{ t('home.signedIn.projects.viewAll') }}
            <PhArrowRight :size="18" aria-hidden="true" />
          </AppButton>
        </div>

        <div class="home-project-panel app-card app-card--sectioned">
          <AppFeedback
            v-if="projectQuery.isPending.value"
            class="home-project-feedback"
            announcement="polite"
          >
            {{ t('home.signedIn.projects.loading') }}
          </AppFeedback>
          <AppFeedback
            v-else-if="projectQuery.isError.value && !projectQuery.data.value"
            class="home-project-feedback"
            announcement="assertive"
            tone="critical"
          >
            {{ t('home.signedIn.projects.loadError') }}
            <template #actions>
              <AppButton
                variant="ghost"
                :disabled="projectQuery.isFetching.value"
                @click="retryProjects"
              >
                {{ t('home.signedIn.projects.retry') }}
              </AppButton>
            </template>
          </AppFeedback>
          <div v-else-if="projects.length === 0" class="home-project-empty">
            <p>{{ t('home.signedIn.projects.empty') }}</p>
            <p>
              {{
                canCreateProjects
                  ? t('home.signedIn.projects.emptyCanCreate')
                  : t('home.signedIn.projects.emptyAsk')
              }}
            </p>
          </div>
          <ul v-else class="home-project-list">
            <li v-for="project in projects" :key="project.id" class="home-project-row">
              <div class="home-project-content">
                <h3>
                  <RouterLink
                    :to="{ name: 'projectOverview', params: { projectId: project.id } }"
                    class="home-project-title-link"
                  >
                    {{ project.display_name }}
                  </RouterLink>
                </h3>
                <p v-if="project.description" class="home-project-description">
                  {{ project.description }}
                </p>
                <dl class="home-project-facts">
                  <div>
                    <dt>{{ t('home.signedIn.projects.team') }}</dt>
                    <dd>{{ project.team.display_name }}</dd>
                  </div>
                  <div>
                    <dt>{{ t('home.signedIn.projects.role') }}</dt>
                    <dd>{{ roleLabel(project.current_user_role) }}</dd>
                  </div>
                </dl>
              </div>
              <AppButton
                :to="{ name: 'projectOverview', params: { projectId: project.id } }"
                variant="ghost"
                class="home-project-open"
                :aria-label="
                  t('home.signedIn.projects.openNamed', { project: project.display_name })
                "
              >
                {{ t('home.signedIn.projects.open') }}
                <PhArrowRight :size="18" aria-hidden="true" />
              </AppButton>
            </li>
          </ul>
          <AppFeedback
            v-if="projectQuery.isError.value && projectQuery.data.value"
            class="home-project-feedback"
            announcement="assertive"
            tone="critical"
          >
            {{ t('home.signedIn.projects.refreshError') }}
            <template #actions>
              <AppButton
                variant="ghost"
                :disabled="projectQuery.isFetching.value"
                @click="retryProjects"
              >
                {{ t('home.signedIn.projects.retry') }}
              </AppButton>
            </template>
          </AppFeedback>
        </div>
      </section>

      <aside class="home-workspace app-card" aria-labelledby="home-workspace-title">
        <h2 id="home-workspace-title">{{ t('home.signedIn.workspace.title') }}</h2>
        <p class="home-workspace-description">
          {{ t('home.signedIn.workspace.description') }}
        </p>
        <div class="home-workspace-access">
          <strong>{{ accountAccess.label }}</strong>
          <p>{{ accountAccess.description }}</p>
        </div>
        <nav :aria-label="t('home.signedIn.workspace.linksLabel')">
          <ul class="home-workspace-links">
            <li v-for="link in workspaceLinks" :key="link.key">
              <RouterLink :to="link.to">
                <span>{{ link.label }}</span>
                <PhArrowRight :size="18" aria-hidden="true" />
              </RouterLink>
            </li>
          </ul>
        </nav>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.home-dashboard {
  container: user-dashboard / inline-size;
  display: grid;
  gap: var(--space-8);
  min-inline-size: 0;
}

.home-dashboard-section-heading {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3) var(--space-6);
}

.home-dashboard-section-heading > div {
  min-inline-size: 0;
}

.home-dashboard-header {
  margin-block-end: 0;
}

.home-dashboard-section-heading p,
.home-workspace-description {
  max-inline-size: 65ch;
  margin: 0;
  color: var(--text-secondary);
  text-wrap: pretty;
}

.home-dashboard-introduction {
  text-wrap: pretty;
}

.home-dashboard-layout {
  display: grid;
  gap: var(--space-8);
  min-inline-size: 0;
}

.home-dashboard-section-heading {
  align-items: end;
  margin-block-end: var(--space-4);
}

.home-dashboard-section-heading h2,
.home-workspace h2 {
  margin: 0 0 var(--space-1);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-title);
}

.home-project-panel {
  min-inline-size: 0;
}

.home-project-feedback {
  margin: var(--space-4);
}

.home-project-empty {
  padding: var(--space-4);
  color: var(--text-secondary);
}

.home-project-empty p {
  margin: 0;
}

.home-project-empty p + p {
  margin-block-start: var(--space-2);
}

.home-project-list,
.home-workspace-links {
  margin: 0;
  padding: 0;
  list-style: none;
}

.home-project-row {
  display: grid;
  gap: var(--space-4);
  min-inline-size: 0;
  padding: var(--space-4);
}

.home-project-row + .home-project-row {
  border-block-start: 1px solid var(--border);
}

.home-project-content {
  min-inline-size: 0;
}

.home-project-content h3 {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-body-strong);
  overflow-wrap: anywhere;
}

.home-project-title-link {
  color: inherit;
  text-decoration: none;
}

.home-project-title-link:hover {
  text-decoration: underline;
  text-underline-offset: 0.2em;
}

.home-project-description {
  max-inline-size: 65ch;
  margin: 0 0 var(--space-3);
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}

.home-project-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-5);
  margin: 0;
  font-size: var(--font-size-small);
}

.home-project-facts > div {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-2);
  min-inline-size: 0;
}

.home-project-facts dt {
  color: var(--text-secondary);
}

.home-project-facts dd {
  min-inline-size: 0;
  margin: 0;
  overflow-wrap: anywhere;
}

.home-project-open {
  justify-self: start;
}

.home-project-open svg,
.home-dashboard-section-heading svg,
.home-workspace-links svg {
  flex-shrink: 0;
}

.home-workspace {
  min-inline-size: 0;
}

.home-workspace-access {
  margin-block: var(--space-5);
}

.home-workspace-access strong {
  display: block;
  margin-block-end: var(--space-1);
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.home-workspace-access p {
  margin: 0;
  color: var(--text-secondary);
}

.home-workspace-links {
  border-block: 1px solid var(--border);
}

.home-workspace-links li + li {
  border-block-start: 1px solid var(--border);
}

.home-workspace-links a {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-block-size: var(--control-min-size);
  padding: var(--space-3) 0;
  color: var(--text-primary);
  font-weight: var(--weight-semibold);
  text-decoration: none;
}

.home-workspace-links a:hover span {
  text-decoration: underline;
  text-underline-offset: 0.2em;
}

@container user-dashboard (min-width: 34rem) {
  .home-project-row {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: start;
  }
}

@container user-dashboard (min-width: 48rem) {
  .home-dashboard-layout {
    grid-template-columns: minmax(0, 1fr) minmax(15rem, 18rem);
    gap: var(--space-8);
  }
}
</style>
