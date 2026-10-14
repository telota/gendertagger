<script setup lang="ts">
import { PhCaretRight } from '@phosphor-icons/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, type RouteLocationRaw } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import { useSessionStore } from '@/stores/session'

import { useProjectIdentity } from '@/composables/useProjectIdentity'
import { useUserPreferences } from '@/composables/useUserPreferences'

interface Breadcrumb {
  id: string
  label: string
  to?: RouteLocationRaw
}

const { t } = useI18n()
const route = useRoute()
const session = useSessionStore()
const identity = useProjectIdentity()
const preferences = useUserPreferences()
const guided = computed(() => preferences.preferences.value?.interface_mode === 'guided')
// Guided mode's project "home base" is Gender taggen, not Übersicht (D26/D27): that page's own cards
// expose the full dataset history and an Übersicht that guided accounts no longer have a path into,
// so the project crumb must not lead there.
const projectHomeRoute = computed(() => (guided.value ? 'projectGenderTagging' : 'projectOverview'))
const projectContext = computed(
  () => identity.isProjectRoute.value && session.canUsePrivateNavigation,
)
const isMembership = computed(() => route.name === 'projectMembers')
const accessUnavailable = computed(() => {
  const error = identity.query.error.value
  return (
    error instanceof ApiError && error.status !== null && [401, 403, 404].includes(error.status)
  )
})
const projectError = computed(
  () => projectContext.value && !isMembership.value && identity.query.isError.value,
)
const projectLoading = computed(
  () => projectContext.value && !isMembership.value && identity.query.isPending.value,
)

const crumbs = computed<Breadcrumb[]>(() => {
  const labels: Record<string, string> = {
    home: t('app.title'),
    legalNotice: t('legal.title'),
    login: t('login.title'),
    changePassword: t('changePassword.title'),
    userSettings: t('header.settings'),
    adminUsers: t('nav.administration'),
    adminTeams: t('adminTeams.title'),
    adminSettings: t('adminSettings.title'),
    projects: t('projects.title'),
    projectMembers: t('projectMembers.title'),
    projectOverview: t('nav.overview'),
    projectGenderTagging: t('nav.genderTagging'),
    projectImport: t('nav.import'),
    projectSnapshots: t('nav.data'),
    snapshotDetail: t('data.detailTitle'),
    projectClassification: t('runs.title'),
    projectReview: t('review.title'),
    projectGame: t('game.title'),
    projectAnnotation: t('nav.review'),
    snapshotAnnotations: t('review.people.title'),
    snapshotRuns: t('runs.title'),
    runDetail: t('runs.detail.title'),
    methodExecutionResults: t('runs.results.title'),
    aggregationDetail: t('aggregations.detail.title'),
    review: t('review.title'),
    game: t('game.title'),
    people: t('review.people.title'),
    evaluations: t('evaluation.title'),
    evaluationDetail: t('evaluation.detail.title'),
    exports: t('export.title'),
    exportDetail: t('export.detail.title'),
    notFound: t('notFound.title'),
  }
  const name = typeof route.name === 'string' ? route.name : 'notFound'
  const current = { id: name, label: labels[name] ?? t('notFound.title') }
  if (!projectContext.value) return [current]
  const project = identity.project.value
  // Every project-scoped trail leads back to the home page (D26: it is now the project hub),
  // including projectOverview itself — previously a dead-end crumb with no way back up.
  const entries: Breadcrumb[] = [{ id: 'home', label: t('app.title'), to: { name: 'home' } }]
  if (project !== null) {
    if (name === projectHomeRoute.value) {
      entries.push({ id: 'project', label: project.display_name })
      return entries
    }
    entries.push({
      id: 'project',
      label: project.display_name,
      to: { name: projectHomeRoute.value, params: { projectId: project.id } },
    })
  } else if (isMembership.value) {
    // Membership management does not imply access to research data or a readable project name.
    entries.push({ id: 'projects', label: t('projects.title'), to: { name: 'projects' } })
  } else {
    entries.push({
      id: 'project-state',
      label: projectLoading.value
        ? t('breadcrumbs.projectLoading')
        : t('breadcrumbs.projectUnavailable'),
    })
  }
  // Only actual, route-supplied parents become links. Never resolve additional scientific resources
  // to manufacture a breadcrumb, or show a run/aggregation/person identifier in the shell.
  if (project !== null && (name === 'snapshotDetail' || name === 'projectImport')) {
    entries.push({
      id: 'projectSnapshots',
      label: t('nav.data'),
      to: { name: 'projectSnapshots', params: { projectId: project.id } },
    })
  } else if (project !== null && (name === 'runDetail' || name === 'methodExecutionResults')) {
    entries.push({
      id: 'snapshotRuns',
      label: t('runs.title'),
      to: {
        name: 'snapshotRuns',
        params: { projectId: project.id, snapshotId: route.params.snapshotId },
      },
    })
    if (name === 'methodExecutionResults') {
      entries.push({
        id: 'runDetail',
        label: t('runs.detail.title'),
        to: {
          name: 'runDetail',
          params: {
            projectId: project.id,
            snapshotId: route.params.snapshotId,
            runId: route.params.runId,
          },
        },
      })
    }
  } else if (project !== null && name === 'exportDetail' && !guided.value) {
    // The exports list is an advanced-only concept (D27: guided mode creates and reaches an export
    // only inline from Gender taggen, never a history of them) — no parent crumb to it there.
    entries.push({
      id: 'exports',
      label: t('export.title'),
      to: { name: 'exports', params: { projectId: project.id, runId: route.params.runId } },
    })
  } else if (project !== null && name === 'evaluationDetail') {
    entries.push({
      id: 'evaluations',
      label: t('evaluation.title'),
      to: { name: 'evaluations', params: { projectId: project.id, runId: route.params.runId } },
    })
  }
  entries.push(current)
  return entries
})
</script>

<template>
  <div class="app-breadcrumb-context">
    <nav
      class="app-breadcrumbs"
      :aria-label="t('breadcrumbs.label')"
      :aria-busy="projectLoading || undefined"
    >
      <ol>
        <li v-for="(crumb, index) in crumbs" :key="crumb.id">
          <PhCaretRight v-if="index > 0" :size="14" aria-hidden="true" />
          <RouterLink v-if="crumb.to" :to="crumb.to">{{ crumb.label }}</RouterLink>
          <span v-else :aria-current="index === crumbs.length - 1 ? 'page' : undefined">{{
            crumb.label
          }}</span>
        </li>
      </ol>
    </nav>
    <div v-if="projectError" class="app-breadcrumb-error">
      <span>{{
        accessUnavailable
          ? t('breadcrumbs.projectAccessUnavailable')
          : t('breadcrumbs.projectLoadError')
      }}</span>
      <RouterLink v-if="accessUnavailable" :to="{ name: 'projects' }">{{
        t('projects.title')
      }}</RouterLink>
      <AppButton v-else variant="text" @click="identity.query.refetch()">{{
        t('header.retry')
      }}</AppButton>
    </div>
  </div>
</template>

<style scoped>
.app-breadcrumb-context {
  min-inline-size: 0;
}

.app-breadcrumbs ol {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-1) var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.app-breadcrumbs li {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  min-inline-size: 0;
  max-inline-size: 100%;
}

.app-breadcrumbs svg {
  flex-shrink: 0;
  align-self: center;
}

.app-breadcrumbs a,
.app-breadcrumbs span {
  min-inline-size: 0;
  overflow-wrap: anywhere;
}

.app-breadcrumbs a {
  color: var(--text-secondary);
  text-underline-offset: 0.2em;
}

.app-breadcrumbs [aria-current='page'] {
  color: var(--text-primary);
  font-weight: var(--weight-semibold);
}

.app-breadcrumb-error {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  margin-block-start: var(--space-1);
  color: var(--critical-text);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}
</style>
