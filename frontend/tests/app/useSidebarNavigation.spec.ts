import { mount } from '@vue/test-utils'
import { defineComponent, reactive, ref } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createAppI18n } from '@/app/i18n'
import { createAppRouter } from '@/app/router'
import { useSidebarNavigation } from '@/app/useSidebarNavigation'
import type { ProjectNavigationContext } from '@/app/useProjectNavigation'

const state = vi.hoisted(() => ({
  project: undefined as unknown,
  access: undefined as unknown,
  availability: undefined as unknown,
  preferences: undefined as unknown,
}))
vi.mock('@/app/useProjectNavigation', () => ({ useProjectNavigation: () => state.project }))
vi.mock('@/composables/useAdminAccess', () => ({ useAdminAccess: () => state.access }))
vi.mock('@/features/tasks/useTaskData', () => ({
  useProjectDataAvailability: () => state.availability,
}))
vi.mock('@/composables/useUserPreferences', () => ({
  useUserPreferences: () => state.preferences,
}))

const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

async function navigationAt(
  name: string,
  role: ProjectNavigationContext['currentUserRole'] = 'operator',
  interfaceMode: 'guided' | 'advanced' = 'advanced',
) {
  const project = ref<ProjectNavigationContext | null>({
    projectId: 'project-a',
    snapshotId: 'snapshot-a',
    runId: 'run-a',
    aggregationId: 'aggregation-a',
    currentUserRole: role,
    currentUserCanManageMembers: true,
    gameModeEnabled: true,
  })
  const session = reactive({ canUsePrivateNavigation: true })
  state.project = project
  state.access = { session, canAccessAdmin: ref(true) }
  const availability = {
    data: ref({
      project_id: 'project-a',
      has_ready_snapshots: true,
      has_completed_aggregations: true,
    }),
    isError: ref(false),
    refetch: vi.fn(),
  }
  state.availability = availability
  const preferences = { preferences: ref({ interface_mode: interfaceMode }) }
  state.preferences = preferences
  const router = createAppRouter(createMemoryHistory())
  const path = router.getRoutes().find((route) => route.name === name)?.path ?? ''
  const params = Object.fromEntries(
    [...path.matchAll(/:(\w+)/g)].map((match) => [match[1], `${match[1]}-a`]),
  )
  await router.push({ name, params })
  let groups!: ReturnType<typeof useSidebarNavigation>
  wrappers.push(
    mount(
      defineComponent({
        setup() {
          groups = useSidebarNavigation()
          return () => null
        },
      }),
      { global: { plugins: [router, createAppI18n('en')] } },
    ),
  )
  return { groups, project, session, availability, preferences }
}

describe('sidebar route ownership', () => {
  it.each([
    ['projectOverview', 'overview'],
    ['projectSnapshots', 'overview'],
    ['snapshotDetail', 'overview'],
    ['projectImport', 'overview'],
    ['projectClassification', 'classification'],
    ['snapshotRuns', 'classification'],
    ['runDetail', 'classification'],
    ['methodExecutionResults', 'classification'],
    ['aggregationDetail', 'classification'],
    ['review', 'review'],
    ['projectReview', 'review'],
    ['projectGame', 'game'],
    ['game', 'game'],
    ['people', 'review'],
    ['projectAnnotation', 'review'],
    ['snapshotAnnotations', 'review'],
    ['evaluations', 'evaluations'],
    ['evaluationDetail', 'evaluations'],
    ['exports', 'exports'],
    ['exportDetail', 'exports'],
    ['adminUsers', 'administration'],
    ['adminTeams', 'teams'],
    ['adminSettings', 'settings'],
  ])('gives %s exactly one current leaf (%s)', async (route, leaf) => {
    const { groups } = await navigationAt(route)
    expect(
      groups.value
        .flatMap((group) => group.items)
        .filter((item) => item.current)
        .map((item) => item.id),
    ).toEqual([leaf])
  })

  it.each(['home', 'legalNotice', 'login', 'changePassword', 'userSettings'])(
    'does not claim the separate %s route',
    async (route) => {
      const { groups } = await navigationAt(route)
      expect(groups.value.flatMap((group) => group.items).filter((item) => item.current)).toEqual(
        [],
      )
    },
  )

  it('shows the Projekte tab only while no project is open, pointing at the home page (D26)', async () => {
    const { groups, project } = await navigationAt('home')
    expect(
      groups.value.flatMap((group) => group.items).some((item) => item.id === 'projects'),
    ).toBe(false)
    project.value = null
    const globalGroup = groups.value.find((group) => group.id === 'global')
    expect(globalGroup?.items.map((item) => [item.id, item.current, item.to])).toEqual([
      ['projects', true, { name: 'home' }],
    ])
  })

  it('uses stable task entry without requiring a selected snapshot or run', async () => {
    const { groups, project } = await navigationAt('projectOverview')
    project.value = { ...project.value!, snapshotId: null, runId: null, aggregationId: null }
    const taskItems = groups.value
      .flatMap((group) => group.items)
      .filter((item) => ['classification', 'review', 'game'].includes(item.id))
    expect(taskItems.map((item) => [item.id, item.to])).toEqual([
      ['classification', { name: 'projectClassification', params: { projectId: 'project-a' } }],
      ['review', { name: 'projectAnnotation', params: { projectId: 'project-a' } }],
      ['game', { name: 'projectGame', params: { projectId: 'project-a' } }],
    ])
    expect(groups.value.some((group) => group.id === 'evaluation')).toBe(false)
    expect(groups.value.flatMap((group) => group.items).every((item) => item.to !== null)).toBe(
      true,
    )
  })

  it('always opens the one annotation entry, whether or not a classification exists (D25)', async () => {
    const { groups, project, availability } = await navigationAt('projectOverview')
    project.value = { ...project.value!, snapshotId: null, runId: null, aggregationId: null }
    for (const hasCompletedAggregations of [false, true]) {
      availability.data.value = {
        project_id: 'project-a',
        has_ready_snapshots: true,
        has_completed_aggregations: hasCompletedAggregations,
      }
      const review = groups.value
        .flatMap((group) => group.items)
        .find((item) => item.id === 'review')
      expect(review?.to).toEqual({ name: 'projectAnnotation', params: { projectId: 'project-a' } })
    }
    availability.data.value = {
      project_id: 'project-a',
      has_ready_snapshots: true,
      has_completed_aggregations: false,
    }
    expect(groups.value.flatMap((group) => group.items).map((item) => item.id)).not.toContain(
      'game',
    )
  })

  it('hides game mode when the project has not enabled it', async () => {
    const { groups, project } = await navigationAt('projectOverview')
    project.value = { ...project.value!, gameModeEnabled: false }
    expect(groups.value.flatMap((group) => group.items).map((item) => item.id)).not.toContain(
      'game',
    )
  })

  it('hides unavailable data tasks without empty groups or disabled destinations', async () => {
    const { groups, project, availability } = await navigationAt('projectOverview')
    project.value = { ...project.value!, snapshotId: null, runId: null, aggregationId: null }
    availability.data.value = {
      project_id: 'project-a',
      has_ready_snapshots: false,
      has_completed_aggregations: false,
    }
    expect(groups.value.flatMap((group) => group.items).map((item) => item.id)).toEqual([
      'overview',
      'administration',
      'teams',
      'settings',
    ])
    expect(groups.value.every((group) => group.items.length > 0)).toBe(true)
  })

  it('hides ineligible destinations instead of offering disabled role-restricted items', async () => {
    const { groups, session } = await navigationAt('people', 'viewer')
    const ids = groups.value.flatMap((group) => group.items).map((item) => item.id)
    expect(ids).not.toContain('data')
    expect(ids).not.toContain('import')
    expect(ids).not.toContain('review')
    expect(ids).not.toContain('people')
    expect(ids).not.toContain('game')
    expect(ids).toContain('exports')
    session.canUsePrivateNavigation = false
    expect(groups.value).toEqual([])
  })
})

describe('guided mode (D26/D27)', () => {
  it('shows only the Gender taggen tab, not the advanced tab set', async () => {
    const { groups } = await navigationAt('projectGenderTagging', 'operator', 'guided')
    const ids = groups.value.flatMap((group) => group.items).map((item) => item.id)
    expect(ids).toContain('genderTagging')
    expect(ids).not.toContain('overview')
    expect(ids).not.toContain('classification')
    expect(ids).not.toContain('review')
    expect(ids).not.toContain('game')
    expect(ids).not.toContain('exports')
  })

  it('marks the gender-ratio page current while visiting it', async () => {
    const { groups } = await navigationAt('projectGenderStatistics', 'operator', 'guided')
    expect(
      groups.value
        .flatMap((group) => group.items)
        .filter((item) => item.current)
        .map((item) => item.id),
    ).toEqual(['genderStatistics'])
  })

  it('marks Gender taggen current on the review workbench and the export page it hands off to', async () => {
    for (const route of ['review', 'projectAnnotation', 'exportDetail']) {
      const { groups } = await navigationAt(route, 'operator', 'guided')
      expect(
        groups.value
          .flatMap((group) => group.items)
          .filter((item) => item.current)
          .map((item) => item.id),
      ).toEqual(['genderTagging'])
    }
  })

  it('shows Statistik & Methoden as its own gender-ratio page, regardless of the URL run (D27 follow-up)', async () => {
    const { groups, project } = await navigationAt('projectGenderTagging', 'operator', 'guided')
    project.value = { ...project.value!, runId: null }
    const items = groups.value.flatMap((group) => group.items)
    const statistics = items.find((entry) => entry.id === 'genderStatistics')
    expect(statistics?.to).toEqual({
      name: 'projectGenderStatistics',
      params: { projectId: 'project-a' },
    })
    expect(items.map((entry) => entry.id)).not.toContain('evaluations')
  })

  it('leaves the advanced tab set unchanged', async () => {
    const { groups } = await navigationAt('projectOverview', 'operator', 'advanced')
    const ids = groups.value.flatMap((group) => group.items).map((item) => item.id)
    expect(ids).not.toContain('genderTagging')
    expect(ids).toContain('overview')
  })
})
