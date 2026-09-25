import {
  PhChartBar,
  PhExport,
  PhFolders,
  PhGearSix,
  PhPencilSimpleLine,
  PhSquaresFour,
  PhTreeStructure,
  PhUploadSimple,
  PhUserList,
  PhUsers,
  PhUsersThree,
} from '@phosphor-icons/vue'
import { computed, type Component, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, type RouteLocationRaw } from 'vue-router'

import { useAdminAccess } from '@/composables/useAdminAccess'
import { hasProjectRole } from '@/features/projects/projectRoles'

import { useProjectNavigation } from './useProjectNavigation'

export interface SidebarNavigationItem {
  id: string
  label: string
  icon: Component
  to: RouteLocationRaw | null
  current: boolean
  unavailableReason?: string
}

export interface SidebarNavigationGroup {
  id: string
  label?: string
  items: SidebarNavigationItem[]
}

/** Each implemented route belongs to one leaf, including detail views with no separate menu item. */
const OWNED_ROUTES: Record<string, readonly string[]> = {
  projects: ['projects'],
  overview: ['projectOverview', 'projectMembers'],
  import: ['projectImport'],
  classification: ['snapshotRuns', 'runDetail', 'aggregationDetail'],
  review: ['review'],
  people: ['people'],
  evaluations: ['evaluations', 'evaluationDetail'],
  exports: ['exports', 'exportDetail'],
  administration: ['adminUsers'],
  teams: ['adminTeams'],
  settings: ['adminSettings'],
}

function link(name: string, params: Record<string, string | null>): RouteLocationRaw | null {
  return Object.values(params).every((value) => value !== null)
    ? { name, params: params as Record<string, string> }
    : null
}

/** One role-aware navigation model shared by the persistent sidebar and the mobile drawer. */
export function useSidebarNavigation(): ComputedRef<SidebarNavigationGroup[]> {
  const { t } = useI18n()
  const route = useRoute()
  const { canAccessAdmin, session } = useAdminAccess()
  const project = useProjectNavigation()

  function item(
    id: string,
    label: string,
    icon: Component,
    to: RouteLocationRaw | null,
  ): SidebarNavigationItem {
    return {
      id,
      label,
      icon,
      to,
      current: typeof route.name === 'string' && (OWNED_ROUTES[id]?.includes(route.name) ?? false),
      ...(to === null
        ? {
            unavailableReason:
              id === 'classification'
                ? t('nav.requiresSnapshot')
                : id === 'review' || id === 'people'
                  ? t('nav.requiresAggregation')
                  : t('nav.requiresRun'),
          }
        : {}),
    }
  }

  return computed(() => {
    if (!session.canUsePrivateNavigation) return []
    const groups: SidebarNavigationGroup[] = [
      {
        id: 'global',
        items: [item('projects', t('nav.projects'), PhFolders, { name: 'projects' })],
      },
    ]
    const current = project.value
    if (current !== null) {
      const { projectId, snapshotId, runId, aggregationId, currentUserRole } = current
      const items = [
        item('overview', t('nav.overview'), PhSquaresFour, link('projectOverview', { projectId })),
      ]
      if (hasProjectRole(currentUserRole, 'operator')) {
        items.push(
          item('import', t('nav.import'), PhUploadSimple, link('projectImport', { projectId })),
        )
      }
      items.push(
        item(
          'classification',
          t('nav.classification'),
          PhTreeStructure,
          link('snapshotRuns', { projectId, snapshotId }),
        ),
      )
      if (hasProjectRole(currentUserRole, 'reviewer')) {
        items.push(
          item(
            'review',
            t('nav.review'),
            PhPencilSimpleLine,
            link('review', { projectId, runId, aggregationId }),
          ),
        )
      }
      items.push(
        item(
          'people',
          t('nav.annotate'),
          PhUserList,
          link('people', { projectId, runId, aggregationId }),
        ),
      )
      groups.push(
        { id: 'project', label: t('nav.currentProject'), items },
        {
          id: 'evaluation',
          label: t('nav.evaluationGroup'),
          items: [
            item(
              'evaluations',
              t('nav.evaluations'),
              PhChartBar,
              link('evaluations', { projectId, runId }),
            ),
            item('exports', t('nav.exports'), PhExport, link('exports', { projectId, runId })),
          ],
        },
      )
    }
    if (canAccessAdmin.value) {
      groups.push({
        id: 'administration',
        label: t('nav.administrationGroup'),
        items: [
          item('administration', t('nav.administration'), PhUsers, { name: 'adminUsers' }),
          item('teams', t('nav.teams'), PhUsersThree, { name: 'adminTeams' }),
          item('settings', t('nav.settings'), PhGearSix, { name: 'adminSettings' }),
        ],
      })
    }
    return groups
  })
}
