<script setup lang="ts">
// The shell's one navigation surface (decision D7); the wireframe's second, redundant tab row is
// dropped. Layout per docs/25-frontend-design-guidelines.md: "a fixed sidebar plus a content region";
// groups per docs/23-wireframe-ui-inventory.md. The optional game path is not part of it (D14).
import {
  PhChartBar,
  PhExport,
  PhFolders,
  PhGearSix,
  PhGenderIntersex,
  PhPencilSimpleLine,
  PhSquaresFour,
  PhTreeStructure,
  PhUploadSimple,
  PhUserList,
  PhUsers,
  PhUsersThree,
} from '@phosphor-icons/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, type RouteLocationRaw } from 'vue-router'

import { useAdminAccess } from '@/composables/useAdminAccess'
import { hasProjectRole } from '@/features/projects/projectRoles'

import NavItem from './NavItem.vue'
import { useProjectNavigation } from './useProjectNavigation'

const { t } = useI18n()
const { canAccessAdmin, session } = useAdminAccess()
const project = useProjectNavigation()
const canImport = computed(() => hasProjectRole(project.value?.currentUserRole, 'operator'))
const canReview = computed(() => hasProjectRole(project.value?.currentUserRole, 'reviewer'))

// A target is `null` while the project has nothing to point at yet (no run, no aggregation).
function link(name: string, params: Record<string, string | null>): RouteLocationRaw | null {
  const complete = Object.values(params).every((value) => value !== null)
  return complete ? { name, params: params as Record<string, string> } : null
}

const projectLinks = computed(() => {
  const current = project.value
  if (current === null) {
    return null
  }
  const { projectId, runId, aggregationId, snapshotId } = current
  return {
    overview: link('projectOverview', { projectId }),
    import: link('projectImport', { projectId }),
    classification: link('snapshotRuns', { projectId, snapshotId }),
    review: link('review', { projectId, runId, aggregationId }),
    people: link('people', { projectId, runId, aggregationId }),
    evaluations: link('evaluations', { projectId, runId }),
    exports: link('exports', { projectId, runId }),
  }
})
</script>

<template>
  <aside class="app-sidebar">
    <RouterLink :to="{ name: 'home' }" class="app-sidebar-brand">
      <PhGenderIntersex :size="24" aria-hidden="true" />
      <span class="app-sidebar-brand-label">{{ t('app.title') }}</span>
    </RouterLink>
    <nav
      v-if="session.canUsePrivateNavigation"
      class="app-sidebar-nav"
      :aria-label="t('nav.label')"
    >
      <ul class="app-sidebar-nav-list">
        <li>
          <NavItem :to="{ name: 'projects' }" :icon="PhFolders" :label="t('nav.projects')" />
        </li>
      </ul>
      <template v-if="projectLinks">
        <h2 class="app-sidebar-group">{{ t('nav.currentProject') }}</h2>
        <ul class="app-sidebar-nav-list">
          <li>
            <NavItem :to="projectLinks.overview" :icon="PhSquaresFour" :label="t('nav.overview')" />
          </li>
          <li v-if="canImport">
            <NavItem :to="projectLinks.import" :icon="PhUploadSimple" :label="t('nav.import')" />
          </li>
          <li>
            <NavItem
              :to="projectLinks.classification"
              :icon="PhTreeStructure"
              :label="t('nav.classification')"
            />
          </li>
          <li v-if="canReview">
            <NavItem
              :to="projectLinks.review"
              :icon="PhPencilSimpleLine"
              :label="t('nav.review')"
            />
          </li>
          <li>
            <NavItem :to="projectLinks.people" :icon="PhUserList" :label="t('nav.annotate')" />
          </li>
        </ul>
        <h2 class="app-sidebar-group">{{ t('nav.evaluationGroup') }}</h2>
        <ul class="app-sidebar-nav-list">
          <li>
            <NavItem
              :to="projectLinks.evaluations"
              :icon="PhChartBar"
              :label="t('nav.evaluations')"
            />
          </li>
          <li>
            <NavItem :to="projectLinks.exports" :icon="PhExport" :label="t('nav.exports')" />
          </li>
        </ul>
      </template>
      <template v-if="canAccessAdmin">
        <h2 class="app-sidebar-group">{{ t('nav.administrationGroup') }}</h2>
        <ul class="app-sidebar-nav-list">
          <li>
            <NavItem
              :to="{ name: 'adminUsers' }"
              :icon="PhUsers"
              :label="t('nav.administration')"
            />
          </li>
          <li>
            <NavItem :to="{ name: 'adminTeams' }" :icon="PhUsersThree" :label="t('nav.teams')" />
          </li>
          <li>
            <NavItem :to="{ name: 'adminSettings' }" :icon="PhGearSix" :label="t('nav.settings')" />
          </li>
        </ul>
      </template>
    </nav>
  </aside>
</template>

<style scoped>
.app-sidebar {
  display: flex;
  flex-direction: column;
  width: 15rem;
  flex-shrink: 0;
  padding: var(--space-4);
  border-right: 1px solid var(--border);
  background: var(--panel);
}

.app-sidebar-brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-6);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  text-decoration: none;
}

.app-sidebar-group {
  margin: var(--space-6) 0 var(--space-2);
  padding: 0 var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-size-body);
  font-weight: var(--weight-semibold);
  text-transform: uppercase;
}

.app-sidebar-nav-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

@media (max-width: 1079px) {
  .app-sidebar {
    width: 3.75rem;
    padding: var(--space-4) var(--space-2);
  }

  .app-sidebar-brand {
    justify-content: center;
  }

  .app-sidebar-brand-label,
  .app-sidebar-group {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
}
</style>
