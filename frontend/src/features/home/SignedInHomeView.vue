<script setup lang="ts">
import { PhArrowRight, PhMinus, PhPlus } from '@phosphor-icons/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRouter, type RouteLocationRaw } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useProjectList } from '@/composables/useProjects'
import { useUserPreferences } from '@/composables/useUserPreferences'
import ProjectCreationForm from '@/features/projects/ProjectCreationForm.vue'
import { useManagedProjects } from '@/features/projects/useManagedProjects'
import { useRoleLabel } from '@/features/projects/useRoleLabel'
import { useSessionStore } from '@/stores/session'

interface WorkspaceLink {
  key: string
  label: string
  to: RouteLocationRaw
}

const { t } = useI18n()
const router = useRouter()
const session = useSessionStore()
const roleLabel = useRoleLabel()
const preferences = useUserPreferences()
// Guided mode has no Übersicht of its own to open (D26/D27): every "open project" entry point here
// goes straight to Gender taggen instead, the same destination the sidebar's one project tab uses.
const projectHomeRoute = computed(() =>
  preferences.preferences.value?.interface_mode === 'guided'
    ? 'projectGenderTagging'
    : 'projectOverview',
)
const displayName = computed(() => session.user?.display_name ?? '')
const canUseProjects = computed(() => session.canUsePrivateNavigation)
const isSignedIn = computed(() => session.status === 'ready' && session.isSignedIn)
const creationOpen = ref(false)
const creationMounted = ref(false)

const query = useProjectList(canUseProjects)
const projects = computed(() => query.data.value?.pages.flatMap((page) => page.items) ?? [])
const managedQuery = useManagedProjects(
  canUseProjects,
  computed(() => session.user?.id ?? null),
)
const additionalManagedProjects = computed(() => {
  const readableIds = new Set(projects.value.map((project) => project.id))
  return (
    managedQuery.data.value?.pages
      .flatMap((page) => page.items)
      .filter((project) => !readableIds.has(project.id)) ?? []
  )
})
// These are additional discovered identities, not proof that an unloaded project has no role.
const showManagedProjects = computed(
  () =>
    managedQuery.isPending.value ||
    managedQuery.isError.value ||
    additionalManagedProjects.value.length > 0 ||
    managedQuery.hasNextPage.value,
)

const canCreateProjects = computed(
  () =>
    isSignedIn.value &&
    !session.mustChangePassword &&
    (session.user?.roles.includes('operator') === true ||
      session.user?.roles.includes('admin') === true),
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

watch([() => session.user?.id, canCreateProjects], () => {
  creationOpen.value = false
  creationMounted.value = false
})

function toggleCreation(): void {
  creationOpen.value = !creationOpen.value
  if (creationOpen.value) creationMounted.value = true
}

function openCreatedProject(projectId: string): void {
  void router.push({ name: projectHomeRoute.value, params: { projectId } })
}

function loadMore(): void {
  if (!query.isFetching.value) void query.fetchNextPage()
}

function loadMoreManaged(): void {
  if (!managedQuery.isFetching.value) void managedQuery.fetchNextPage()
}
</script>

<template>
  <div class="home-dashboard">
    <header class="home-dashboard-header app-page-heading">
      <h1 class="home-dashboard-title app-page-heading__title">
        {{ t('home.signedIn.welcomeBack', { name: displayName }) }}
      </h1>
      <p class="home-dashboard-introduction app-page-heading__description">
        {{ t('home.signedIn.introduction') }}
      </p>
    </header>

    <div class="home-dashboard-layout">
      <section aria-labelledby="home-projects-title">
        <div class="home-dashboard-section-heading">
          <div>
            <h2 id="home-projects-title">{{ t('projects.title') }}</h2>
          </div>
          <AppButton
            v-if="canCreateProjects"
            class="home-new-project"
            :variant="creationOpen ? 'ghost' : 'solid'"
            :aria-expanded="creationOpen"
            aria-controls="home-project-creation-panel"
            @click="toggleCreation"
          >
            <PhMinus v-if="creationOpen" :size="18" aria-hidden="true" />
            <PhPlus v-else :size="18" aria-hidden="true" />
            {{ creationOpen ? t('projects.hideCreation') : t('projects.newProject') }}
          </AppButton>
        </div>

        <div
          v-if="canCreateProjects"
          v-show="creationOpen"
          id="home-project-creation-panel"
          class="home-project-creation"
        >
          <ProjectCreationForm
            v-if="creationMounted && session.user"
            :key="session.user.id"
            :principal-id="session.user.id"
            :is-administrator="isAdministrator"
            @created="openCreatedProject"
          />
        </div>

        <div class="home-project-panel app-card app-card--sectioned">
          <AppFeedback
            v-if="query.isPending.value"
            class="home-project-feedback"
            announcement="polite"
          >
            {{ t('projects.loading') }}
          </AppFeedback>
          <AppFeedback
            v-else-if="query.isError.value && !query.data.value"
            class="home-project-feedback"
            announcement="assertive"
            tone="critical"
          >
            {{ t('projects.loadError') }}
            <template #actions>
              <AppButton
                variant="ghost"
                :disabled="query.isFetching.value"
                @click="() => query.refetch()"
              >
                {{ t('projects.retry') }}
              </AppButton>
            </template>
          </AppFeedback>
          <template v-else>
            <div v-if="projects.length === 0" class="home-project-empty">
              <p>{{ t('projects.empty') }}</p>
              <p v-if="canCreateProjects">{{ t('projects.emptyCreateHint') }}</p>
              <p v-else>{{ t('projects.emptyHint') }}</p>
            </div>
            <ul v-else class="home-project-list">
              <li v-for="project in projects" :key="project.id" class="home-project-row">
                <div class="home-project-content">
                  <h3>
                    <RouterLink
                      :to="{ name: projectHomeRoute, params: { projectId: project.id } }"
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
                      <dt>{{ t('projects.team') }}</dt>
                      <dd>{{ project.team.display_name }}</dd>
                    </div>
                    <div>
                      <dt>{{ t('projects.yourRole') }}</dt>
                      <dd>{{ roleLabel(project.current_user_role) }}</dd>
                    </div>
                  </dl>
                </div>
                <div class="home-project-actions">
                  <AppButton
                    :to="{ name: projectHomeRoute, params: { projectId: project.id } }"
                    variant="ghost"
                    class="home-project-open"
                    :aria-label="t('projects.openProjectNamed', { project: project.display_name })"
                  >
                    {{ t('projects.openProject') }}
                    <PhArrowRight :size="18" aria-hidden="true" />
                  </AppButton>
                  <AppButton
                    v-if="project.current_user_can_manage_members"
                    :to="{ name: 'projectMembers', params: { projectId: project.id } }"
                    variant="ghost"
                    class="home-project-manage-members"
                    :aria-label="t('projects.manageMembersNamed', { project: project.display_name })"
                  >
                    {{ t('projects.manageMembers') }}
                  </AppButton>
                </div>
              </li>
            </ul>
            <AppFeedback
              v-if="query.isError.value"
              class="home-project-feedback"
              announcement="assertive"
              tone="critical"
            >
              {{
                query.isFetchNextPageError.value
                  ? t('projects.loadMoreError')
                  : t('projects.loadError')
              }}
              <template v-if="!query.isFetchNextPageError.value" #actions>
                <AppButton
                  variant="ghost"
                  :disabled="query.isFetching.value"
                  @click="() => query.refetch()"
                >
                  {{ t('projects.retry') }}
                </AppButton>
              </template>
            </AppFeedback>
            <AppFeedback
              v-if="query.isFetchingNextPage.value"
              class="home-project-feedback"
              announcement="polite"
            >
              {{ t('projects.loadingMore') }}
            </AppFeedback>
            <AppButton
              v-if="query.hasNextPage.value"
              class="home-project-load-more"
              variant="ghost"
              :disabled="query.isFetching.value"
              @click="loadMore"
            >
              {{ query.isFetchNextPageError.value ? t('projects.retry') : t('projects.loadMore') }}
            </AppButton>
          </template>
        </div>

        <section
          v-if="showManagedProjects"
          class="home-project-managed"
          aria-labelledby="home-project-managed-title"
        >
          <h2 id="home-project-managed-title">{{ t('projects.managedTitle') }}</h2>
          <p class="home-project-managed-description">{{ t('projects.managedDescription') }}</p>
          <AppFeedback v-if="managedQuery.isPending.value" announcement="polite">
            {{ t('projects.managedLoading') }}
          </AppFeedback>
          <ul v-if="additionalManagedProjects.length" class="home-project-list">
            <li
              v-for="project in additionalManagedProjects"
              :key="project.id"
              class="home-project-row"
            >
              <div class="home-project-content">
                <h3>{{ project.display_name }}</h3>
                <dl class="home-project-facts">
                  <div>
                    <dt>{{ t('projects.team') }}</dt>
                    <dd>{{ project.team.display_name }}</dd>
                  </div>
                </dl>
              </div>
              <div class="home-project-actions">
                <AppButton
                  :to="{ name: 'projectMembers', params: { projectId: project.id } }"
                  variant="ghost"
                  class="home-project-manage-members"
                  :aria-label="t('projects.manageMembersNamed', { project: project.display_name })"
                  >{{ t('projects.manageMembers') }}</AppButton
                >
              </div>
            </li>
          </ul>
          <AppFeedback
            v-if="managedQuery.isError.value"
            announcement="assertive"
            tone="critical"
            class="home-project-feedback"
          >
            {{
              managedQuery.isFetchNextPageError.value
                ? t('projects.managedLoadMoreError')
                : t('projects.managedLoadError')
            }}
            <template v-if="!managedQuery.isFetchNextPageError.value" #actions>
              <AppButton
                variant="ghost"
                :disabled="managedQuery.isFetching.value"
                @click="() => managedQuery.refetch()"
                >{{ t('projects.retry') }}</AppButton
              >
            </template>
          </AppFeedback>
          <AppFeedback
            v-if="managedQuery.isFetchingNextPage.value"
            announcement="polite"
            class="home-project-feedback"
          >
            {{ t('projects.managedLoading') }}
          </AppFeedback>
          <AppButton
            v-if="managedQuery.hasNextPage.value"
            class="home-project-managed-load-more"
            variant="ghost"
            :disabled="managedQuery.isFetching.value"
            @click="loadMoreManaged"
          >
            {{
              managedQuery.isFetchNextPageError.value
                ? t('projects.retry')
                : t('projects.loadMoreManaged')
            }}
          </AppButton>
        </section>
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

.home-new-project svg {
  flex-shrink: 0;
}

.home-project-creation {
  margin-block-end: var(--space-8);
}

.home-project-panel {
  min-inline-size: 0;
}

.home-project-feedback {
  margin: var(--space-4) 0 0;
}

.home-project-empty {
  color: var(--text-secondary);
}

.home-project-empty p {
  margin: 0;
}

.home-project-empty p + p {
  margin-block-start: var(--space-2);
}

.home-project-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: var(--space-4);
}

.home-project-row {
  display: grid;
  gap: var(--space-4) var(--space-6);
  min-inline-size: 0;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card, var(--radius-input));
  background: var(--panel);
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

.home-project-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.home-project-actions svg {
  flex-shrink: 0;
}

.home-project-load-more,
.home-project-managed-load-more,
.home-project-feedback {
  margin-block-start: var(--space-4);
}

.home-project-managed {
  margin-block-start: var(--space-10);
  padding-block-start: var(--space-6);
  border-block-start: 1px solid var(--border);
}

.home-project-managed h2 {
  margin: 0 0 var(--space-2);
}

.home-project-managed-description {
  margin-block-end: var(--space-4);
  color: var(--text-secondary);
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
  margin: 0;
  padding: 0;
  list-style: none;
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

.home-workspace-links svg {
  flex-shrink: 0;
}

@container user-dashboard (min-width: 40rem) {
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
