<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useSessionStore } from '@/stores/session'

import { useCreateProject, useProjectList } from './useProjects'

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
const canCreateProject = computed(
  () => session.user?.roles.some((role) => role === 'operator' || role === 'admin') ?? false,
)

const query = useProjectList(isSignedIn)
const projects = computed(() => query.data.value?.pages.flatMap((page) => page.items) ?? [])

function roleLabel(role: string): string {
  switch (role) {
    case 'viewer':
      return t('projects.role.viewer')
    case 'reviewer':
      return t('projects.role.reviewer')
    case 'operator':
      return t('projects.role.operator')
    default:
      return role
  }
}

function loadMore(): void {
  void query.fetchNextPage()
}

const isCreating = ref(false)
const displayName = ref('')
const slug = ref('')
const description = ref('')
const creation = useCreateProject()

function creationErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'validation_error':
        return t('projects.new.errors.validation')
      case 'resource_conflict':
        return t('projects.new.errors.conflict')
      case 'network_error':
        return t('projects.new.errors.network')
    }
  }
  return t('projects.new.errors.generic')
}

function openCreateForm(): void {
  isCreating.value = true
}

function cancelCreateForm(): void {
  isCreating.value = false
  displayName.value = ''
  slug.value = ''
  description.value = ''
  creation.reset()
}

async function submitCreateForm(): Promise<void> {
  try {
    await creation.mutateAsync({
      displayName: displayName.value,
      slug: slug.value,
      description: description.value,
    })
    cancelCreateForm()
  } catch {
    // creation.isError/creation.error already reflect this; the form stays open to show it.
  }
}
</script>

<template>
  <main class="project-list">
    <h1 class="project-list-title">{{ t('projects.title') }}</h1>

    <p v-if="session.status === 'idle' || session.status === 'loading'" role="status">
      {{ t('projects.loading') }}
    </p>
    <div v-else-if="session.status === 'error'" class="project-list-load-error">
      <p role="alert">{{ t('projects.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('projects.retry') }}</AppButton>
    </div>
    <template v-else-if="isSignedIn">
      <AppButton
        v-if="canCreateProject && !isCreating"
        class="project-list-new-project"
        type="button"
        @click="openCreateForm"
      >
        {{ t('projects.new.action') }}
      </AppButton>

      <form
        v-if="isCreating"
        class="project-list-form"
        novalidate
        @submit.prevent="submitCreateForm"
      >
        <AppTextField
          id="new-project-display-name"
          v-model="displayName"
          name="display-name"
          :label="t('projects.new.displayName')"
          required
        />
        <AppTextField
          id="new-project-slug"
          v-model="slug"
          name="slug"
          :label="t('projects.new.slug')"
          required
        />
        <AppTextField
          id="new-project-description"
          v-model="description"
          name="description"
          :label="t('projects.new.description')"
        />
        <p v-if="creation.isError.value" role="alert" class="project-list-error">
          {{ creationErrorMessage(creation.error.value) }}
        </p>
        <div class="project-list-form-actions">
          <AppButton
            class="project-list-cancel-create"
            variant="ghost"
            type="button"
            @click="cancelCreateForm"
          >
            {{ t('projects.new.cancel') }}
          </AppButton>
          <AppButton
            class="project-list-submit-create"
            type="submit"
            :disabled="creation.isPending.value"
          >
            {{ creation.isPending.value ? t('projects.new.submitting') : t('projects.new.submit') }}
          </AppButton>
        </div>
      </form>

      <p v-if="query.isPending.value" role="status">{{ t('projects.loading') }}</p>
      <div v-else-if="query.isError.value" class="project-list-load-error">
        <p role="alert">{{ t('projects.loadError') }}</p>
        <AppButton class="project-list-retry" type="button" @click="() => query.refetch()">
          {{ t('projects.retry') }}
        </AppButton>
      </div>
      <template v-else>
        <p v-if="projects.length === 0" class="project-list-empty">{{ t('projects.empty') }}</p>
        <ul v-else class="project-list-items">
          <li v-for="project in projects" :key="project.id" class="project-card">
            <h2 class="project-card-title">{{ project.display_name }}</h2>
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

.project-list-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
}

.project-list-load-error p,
.project-list-error {
  margin: 0;
  color: var(--critical);
}

.project-list-form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.project-list-form-actions {
  display: flex;
  gap: var(--space-3);
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

.project-card-description {
  margin: 0 0 var(--space-2);
  color: var(--text-secondary);
}

.project-card-role {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}
</style>
