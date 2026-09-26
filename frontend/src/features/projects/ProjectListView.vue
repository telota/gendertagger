<script setup lang="ts">
import { PhArrowRight, PhMinus, PhPlus } from '@phosphor-icons/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useSessionStore } from '@/stores/session'

import ProjectCreationForm from './ProjectCreationForm.vue'
import { useManagedProjects } from './useManagedProjects'
import { useProjectList } from './useProjects'
import { useRoleLabel } from './useRoleLabel'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const creationOpen = ref(false)
const creationMounted = ref(false)

// Wait for session initialization before redirecting; a failed check has its own recovery action.
watch(
  () => session.status,
  (status) => {
    if (status === 'ready' && !session.isSignedIn) {
      void router.replace({ name: 'login', query: { redirect: route.fullPath } })
    }
  },
  { immediate: true },
)

const isSignedIn = computed(() => session.status === 'ready' && session.isSignedIn)
const canUseProjects = computed(() => session.canUsePrivateNavigation)
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
const roleLabel = useRoleLabel()
// Same-account reauthentication temporarily disables shell navigation, but must retain this draft.
const canCreateProject = computed(
  () =>
    isSignedIn.value &&
    !session.mustChangePassword &&
    (session.user?.roles.includes('operator') === true ||
      session.user?.roles.includes('admin') === true),
)

watch([() => session.user?.id, canCreateProject], () => {
  creationOpen.value = false
  creationMounted.value = false
})

function toggleCreation(): void {
  creationOpen.value = !creationOpen.value
  if (creationOpen.value) creationMounted.value = true
}

function retrySession(): void {
  void session.initialize()
}

function openCreatedProject(projectId: string): void {
  void router.push({ name: 'projectOverview', params: { projectId } })
}

function loadMore(): void {
  if (!query.isFetching.value) void query.fetchNextPage()
}

function loadMoreManaged(): void {
  if (!managedQuery.isFetching.value) void managedQuery.fetchNextPage()
}
</script>

<template>
  <main class="project-list app-page-frame">
    <header class="project-list-heading app-page-heading">
      <h1 class="project-list-title app-page-heading__title">{{ t('projects.title') }}</h1>
      <div v-if="canCreateProject" class="app-page-heading__actions">
        <AppButton
          class="project-list-new-project"
          :variant="creationOpen ? 'ghost' : 'solid'"
          :aria-expanded="creationOpen"
          aria-controls="project-creation-panel"
          @click="toggleCreation"
        >
          <PhMinus v-if="creationOpen" :size="18" aria-hidden="true" />
          <PhPlus v-else :size="18" aria-hidden="true" />
          {{ creationOpen ? t('projects.hideCreation') : t('projects.newProject') }}
        </AppButton>
      </div>
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
      class="app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('projects.sessionLoadError') }}
      <template #actions>
        <AppButton variant="ghost" @click="retrySession">{{ t('projects.retry') }}</AppButton>
      </template>
    </AppFeedback>
    <template v-else-if="isSignedIn">
      <div
        v-if="canCreateProject"
        v-show="creationOpen"
        id="project-creation-panel"
        class="project-list-creation"
      >
        <ProjectCreationForm
          v-if="creationMounted && session.user"
          :key="session.user.id"
          :principal-id="session.user.id"
          :is-administrator="session.user.roles.includes('admin')"
          @created="openCreatedProject"
        />
      </div>

      <div class="project-list-readable">
        <AppFeedback v-if="query.isPending.value" class="app-card" announcement="polite">{{
          t('projects.loading')
        }}</AppFeedback>
        <AppFeedback
          v-else-if="query.isError.value && !query.data.value"
          class="app-card"
          announcement="assertive"
          tone="critical"
        >
          {{ t('projects.loadError') }}
          <template #actions>
            <AppButton
              class="project-list-retry"
              variant="ghost"
              :disabled="query.isFetching.value"
              @click="() => query.refetch()"
            >
              {{ t('projects.retry') }}
            </AppButton>
          </template>
        </AppFeedback>
        <template v-else>
          <div v-if="projects.length === 0" class="project-list-empty app-card">
            <p>{{ t('projects.empty') }}</p>
            <p v-if="canCreateProject">{{ t('projects.emptyCreateHint') }}</p>
            <p v-else>{{ t('projects.emptyHint') }}</p>
          </div>
          <ul v-else class="project-list-items">
            <li
              v-for="project in projects"
              :key="project.id"
              class="project-card app-resource-card"
            >
              <div class="project-card-content">
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
                <dl class="project-card-facts">
                  <div>
                    <dt>{{ t('projects.team') }}</dt>
                    <dd>{{ project.team.display_name }}</dd>
                  </div>
                  <div>
                    <dt>{{ t('projects.yourRole') }}</dt>
                    <dd class="project-card-role">{{ roleLabel(project.current_user_role) }}</dd>
                  </div>
                </dl>
              </div>
              <div class="project-card-actions">
                <AppButton
                  :to="{ name: 'projectOverview', params: { projectId: project.id } }"
                  variant="ghost"
                  class="project-card-open-project"
                  :aria-label="t('projects.openProjectNamed', { project: project.display_name })"
                >
                  {{ t('projects.openProject') }}
                  <PhArrowRight :size="18" aria-hidden="true" />
                </AppButton>
                <AppButton
                  v-if="project.current_user_can_manage_members"
                  :to="{ name: 'projectMembers', params: { projectId: project.id } }"
                  variant="ghost"
                  class="project-card-manage-members"
                  :aria-label="t('projects.manageMembersNamed', { project: project.display_name })"
                >
                  {{ t('projects.manageMembers') }}
                </AppButton>
              </div>
            </li>
          </ul>
          <AppFeedback
            v-if="query.isError.value"
            announcement="assertive"
            tone="critical"
            class="project-list-feedback app-card"
          >
            {{
              query.isFetchNextPageError.value
                ? t('projects.loadMoreError')
                : t('projects.loadError')
            }}
            <template v-if="!query.isFetchNextPageError.value" #actions>
              <AppButton
                class="project-list-retry"
                variant="ghost"
                :disabled="query.isFetching.value"
                @click="() => query.refetch()"
                >{{ t('projects.retry') }}</AppButton
              >
            </template>
          </AppFeedback>
          <AppFeedback
            v-if="query.isFetchingNextPage.value"
            announcement="polite"
            class="project-list-feedback app-card"
          >
            {{ t('projects.loadingMore') }}
          </AppFeedback>
          <AppButton
            v-if="query.hasNextPage.value"
            class="project-list-load-more"
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
        class="project-list-managed"
        aria-labelledby="project-list-managed-title"
      >
        <h2 id="project-list-managed-title">{{ t('projects.managedTitle') }}</h2>
        <p class="project-list-managed-description">{{ t('projects.managedDescription') }}</p>
        <AppFeedback v-if="managedQuery.isPending.value" class="app-card" announcement="polite">
          {{ t('projects.managedLoading') }}
        </AppFeedback>
        <ul v-if="additionalManagedProjects.length" class="project-list-items">
          <li
            v-for="project in additionalManagedProjects"
            :key="project.id"
            class="project-card app-resource-card"
          >
            <div class="project-card-content">
              <h3 class="project-card-title">{{ project.display_name }}</h3>
              <dl class="project-card-facts">
                <div>
                  <dt>{{ t('projects.team') }}</dt>
                  <dd>{{ project.team.display_name }}</dd>
                </div>
              </dl>
            </div>
            <div class="project-card-actions">
              <AppButton
                :to="{ name: 'projectMembers', params: { projectId: project.id } }"
                variant="ghost"
                class="project-card-manage-members"
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
          class="project-list-feedback app-card"
        >
          {{
            managedQuery.isFetchNextPageError.value
              ? t('projects.managedLoadMoreError')
              : t('projects.managedLoadError')
          }}
          <template v-if="!managedQuery.isFetchNextPageError.value" #actions>
            <AppButton
              class="project-list-managed-retry"
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
          class="project-list-feedback app-card"
        >
          {{ t('projects.managedLoading') }}
        </AppFeedback>
        <AppButton
          v-if="managedQuery.hasNextPage.value"
          class="project-list-managed-load-more"
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
    </template>
  </main>
</template>

<style scoped>
.project-list {
  container: project-index / inline-size;
}

.project-list-creation {
  margin-block-end: var(--space-8);
}

.project-list-empty {
  color: var(--text-secondary);
}

.project-list-empty p,
.project-list-managed-description {
  max-inline-size: 65ch;
  margin: 0 0 var(--space-2);
}

.project-list-items {
  display: grid;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}

.project-card {
  display: grid;
  gap: var(--space-4) var(--space-6);
}

.project-card-content,
.project-card-actions {
  min-inline-size: 0;
}

.project-card-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-title);
  overflow-wrap: anywhere;
}

.project-card-link {
  color: inherit;
  text-decoration: none;
}

.project-card-link:hover {
  text-decoration: underline;
  text-underline-offset: 0.2em;
}

.project-card-description {
  max-inline-size: 65ch;
  margin: 0 0 var(--space-3);
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}

.project-card-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-6);
  margin: 0;
  font-size: var(--font-size-small);
}

.project-card-facts > div {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-2);
  min-inline-size: 0;
}

.project-card-facts dt {
  color: var(--text-secondary);
}

.project-card-facts dd {
  min-inline-size: 0;
  margin: 0;
  overflow-wrap: anywhere;
}

.project-card-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.project-card-actions svg,
.project-list-new-project svg {
  flex-shrink: 0;
}

.project-list-load-more,
.project-list-managed-load-more,
.project-list-feedback {
  margin-block-start: var(--space-4);
}

.project-list-managed {
  margin-block-start: var(--space-10);
  padding-block-start: var(--space-6);
  border-block-start: 1px solid var(--border);
}

.project-list-managed h2 {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.project-list-managed-description {
  margin-block-end: var(--space-4);
  color: var(--text-secondary);
}

@container project-index (min-width: 40rem) {
  .project-card {
    grid-template-columns: minmax(0, 1fr) minmax(0, 13rem);
    align-items: start;
  }

  .project-card-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
