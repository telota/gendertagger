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
import { useAggregation } from '@/composables/useAggregations'
import { hasProjectRole } from '@/composables/projectRoles'
import { useProject } from '@/composables/useProjects'
import { useUserPreferences } from '@/composables/useUserPreferences'
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
  // Guided mode's one project page (D27) also owns the full review workbench and the export detail
  // page it hands off to: both are reached only from here in that presentation, and nothing else in
  // the guided tab set represents them.
  genderTagging: [
    'projectGenderTagging',
    'review',
    'projectAnnotation',
    'snapshotAnnotations',
    'people',
    'exports',
    'exportDetail',
  ],
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
  const preferences = useUserPreferences()
  // Advanced, not the account default of guided (ADR-0050), while the preference is still loading
  // or failed to load: never hide capability over a transient gap — once it resolves, this follows
  // whatever the account actually has stored.
  const interfaceMode = computed(() => preferences.preferences.value?.interface_mode ?? 'advanced')
  const availability = useProjectDataAvailability(
    computed(() => project.value?.projectId ?? ''),
    computed(
      () =>
        project.value !== null &&
        project.value.currentUserRole !== null &&
        interfaceMode.value !== 'guided',
    ),
  )
  // Guided mode's one project page (D27) carries no runId of its own: the URL never names a run or
  // aggregation. "Statistik & Methoden" still needs one to link to, so — guided only — fall back to
  // the project's working aggregation (ADR-0035) and read the run it was built from. Advanced mode's
  // runId stays exactly what useProjectNavigation resolves from the URL, unchanged.
  const needsWorkingAggregationFallback = computed(
    () => interfaceMode.value === 'guided' && project.value !== null && project.value.runId === null,
  )
  const projectRecord = useProject(
    computed(() => project.value?.projectId ?? ''),
    needsWorkingAggregationFallback,
  )
  const workingAggregationId = computed(
    () => projectRecord.data.value?.working_aggregation_execution_id ?? null,
  )
  const workingAggregation = useAggregation(
    computed(() => workingAggregationId.value ?? ''),
    // Gated on the fallback itself, not just a non-null id: `projectRecord` shares its query key
    // with the project fetch `useProjectIdentity` already runs, so its data can arrive from that
    // cache even while disabled here — advanced mode must not let that leak into an aggregation
    // fetch it never needed.
    computed(() => needsWorkingAggregationFallback.value && workingAggregationId.value !== null),
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
      const guided = interfaceMode.value === 'guided'
      const items: SidebarNavigationItem[] = []
      const additionalItems: SidebarNavigationItem[] = []
      if (currentUserRole !== null) {
        if (guided) {
          // Guided mode (D26/D27): one tab for the whole import→generate→review→export flow. Its
          // own page covers what overview/classification/export used to show; review and game stay
          // full separate pages, reached only from there (OWNED_ROUTES.genderTagging above).
          items.push(
            item(
              'genderTagging',
              t('nav.genderTagging'),
              PhPencilSimpleLine,
              link('projectGenderTagging', { projectId }),
            ),
          )
        } else {
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
      }
      if (items.length) {
        groups.push({
          id: 'project',
          items,
          ...(!guided && currentUserRole !== null && availability.data.value === undefined
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
      const evaluationsRunId = guided ? (runId ?? workingAggregation.data.value?.run_id ?? null) : runId
      if (currentUserRole !== null && evaluationsRunId !== null) {
        groups.push({
          id: 'evaluation',
          label: t('nav.evaluationGroup'),
          items: [
            item(
              'evaluations',
              t('nav.evaluations'),
              PhChartBar,
              link('evaluations', { projectId, runId: evaluationsRunId }),
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
