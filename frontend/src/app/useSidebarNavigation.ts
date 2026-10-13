import {
  PhChartBar,
  PhExport,
  PhFolders,
  PhGearSix,
  PhGameController,
  PhPencilSimpleLine,
  PhSquaresFour,
  PhTreeStructure,
  PhUsers,
  PhUsersThree,
} from '@phosphor-icons/vue'
import { computed, type Component, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, type RouteLocationRaw } from 'vue-router'

import { useAdminAccess } from '@/composables/useAdminAccess'
import { hasProjectRole } from '@/composables/projectRoles'
import { useProjectDataAvailability } from '@/features/tasks/useTaskData'

import { useProjectNavigation } from './useProjectNavigation'

interface SidebarNavigationItem {
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
  availability?: { status: 'loading' | 'error'; retry: () => void }
}

/** Each implemented route belongs to one leaf, including detail views with no separate menu item. */
const OWNED_ROUTES: Record<string, readonly string[]> = {
  // The "Projekte" tab now opens the signed-in home page (D26): the project list, "Projekt
  // anlegen", and per-project "Mitglieder verwalten" moved there, out of the project-scoped group
  // below. The `projects` route itself is unchanged and still reachable — only the sidebar stopped
  // linking to it.
  projects: ['home'],
  // Daten is folded into Übersicht (decision, 2026-09-30): the history page and the legacy direct-
  // import route have no nav item of their own, but still highlight Übersicht as the current leaf.
  overview: ['projectOverview', 'projectSnapshots', 'snapshotDetail', 'projectImport'],
  classification: [
    'projectClassification',
    'snapshotRuns',
    'runDetail',
    'methodExecutionResults',
    'aggregationDetail',
  ],
  // Redigieren and Manuell annotieren are one sidebar entry (D24, 2026-09-30): whichever route it
  // resolves to for the current data state, and the plain register it can still lead to, all
  // highlight the same leaf.
  review: ['projectReview', 'review', 'projectAnnotation', 'snapshotAnnotations', 'people'],
  game: ['projectGame', 'game'],
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
  const availability = useProjectDataAvailability(
    computed(() => project.value?.projectId ?? ''),
    computed(() => project.value !== null && project.value.currentUserRole !== null),
  )

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
    }
  }

  return computed(() => {
    if (!session.canUsePrivateNavigation) return []
    const current = project.value
    // The "Projekte" tab and a project's own tabs never show at once (D26): it opens the signed-in
    // home page, which now owns the project list, and is shown only while no project is open —
    // the per-project group below replaces it for the duration of that project.
    const groups: SidebarNavigationGroup[] =
      current === null
        ? [
            {
              id: 'global',
              items: [item('projects', t('nav.projects'), PhFolders, { name: 'home' })],
            },
          ]
        : []
    if (current !== null) {
      const { projectId, runId, currentUserRole, gameModeEnabled } = current
      const items: SidebarNavigationItem[] = []
      const additionalItems: SidebarNavigationItem[] = []
      if (currentUserRole !== null) {
        items.push(
          item(
            'overview',
            t('nav.overview'),
            PhSquaresFour,
            link('projectOverview', { projectId }),
          ),
        )
        if (availability.data.value?.has_ready_snapshots) {
          items.push(
            item(
              'classification',
              t('nav.classification'),
              PhTreeStructure,
              link('projectClassification', { projectId }),
            ),
          )
        }
        if (
          hasProjectRole(currentUserRole, 'reviewer') &&
          availability.data.value?.has_ready_snapshots
        ) {
          // One tab, one destination, always (decision D25): the entry decides per dataset — its own
          // working classification if there is one, plain manual annotation otherwise — and can still
          // load an older dataset from its own list. That per-dataset decision cannot be made correctly
          // at the project level: a project can hold both a classified and an unclassified dataset at
          // once, and a single project-wide branch (D24) picked the wrong one for whichever wasn't newest.
          items.push(
            item(
              'review',
              t('nav.review'),
              PhPencilSimpleLine,
              link('projectAnnotation', { projectId }),
            ),
          )
          if (availability.data.value?.has_completed_aggregations === true && gameModeEnabled) {
            additionalItems.push(
              item('game', t('nav.game'), PhGameController, link('projectGame', { projectId })),
            )
          }
        }
        // Directly after Redigieren, ahead of Statistik & Methoden (D26) — a reordering only; the
        // same `runId` gate as before, now applied to this one item instead of a shared group.
        if (runId !== null) {
          items.push(
            item('exports', t('nav.exports'), PhExport, link('exports', { projectId, runId })),
          )
        }
      }
      if (items.length) {
        groups.push({
          id: 'project',
          items,
          ...(currentUserRole !== null && availability.data.value === undefined
            ? {
                availability: {
                  status: availability.isError.value ? ('error' as const) : ('loading' as const),
                  retry: () => {
                    void availability.refetch()
                  },
                },
              }
            : {}),
        })
      }
      if (additionalItems.length) {
        groups.push({
          id: 'additional',
          label: t('nav.additionalGroup'),
          items: additionalItems,
        })
      }
      if (currentUserRole !== null && runId !== null) {
        groups.push({
          id: 'evaluation',
          label: t('nav.evaluationGroup'),
          items: [
            item(
              'evaluations',
              t('nav.evaluations'),
              PhChartBar,
              link('evaluations', { projectId, runId }),
            ),
          ],
        })
      }
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
