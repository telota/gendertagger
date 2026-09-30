import { mount } from '@vue/test-utils'
import { defineComponent, reactive, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createAppI18n } from '@/app/i18n'
import { routes } from '@/app/router'
import { useSidebarNavigation } from '@/app/useSidebarNavigation'
import type { ProjectNavigationContext } from '@/app/useProjectNavigation'

const state = vi.hoisted(() => ({
  project: undefined as unknown,
  access: undefined as unknown,
  availability: undefined as unknown,
}))
vi.mock('@/app/useProjectNavigation', () => ({ useProjectNavigation: () => state.project }))
vi.mock('@/composables/useAdminAccess', () => ({ useAdminAccess: () => state.access }))
vi.mock('@/features/tasks/useTaskData', () => ({
  useProjectDataAvailability: () => state.availability,
}))

const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => wrappers.splice(0).forEach((wrapper) => wrapper.unmount()))

async function navigationAt(
  name: string,
  role: ProjectNavigationContext['currentUserRole'] = 'operator',
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
  const router = createRouter({
    history: createMemoryHistory(),
    routes: routes.map((route) => ({
      path: route.path,
      name: route.name,
      component: { render: () => null },
    })),
  })
  const path = routes.find((route) => route.name === name)?.path ?? ''
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
  return { groups, project, session, availability }
}

describe('sidebar route ownership', () => {
  it.each([
    ['projects', 'projects'],
    ['projectOverview', 'overview'],
    ['projectMembers', 'projectMembers'],
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
    ['people', 'people'],
    ['projectAnnotation', 'people'],
    ['snapshotAnnotations', 'people'],
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

  it('offers only Members in a management-only project context', async () => {
    const { groups, project } = await navigationAt('projectMembers', null)
    project.value = { ...project.value!, runId: null, snapshotId: null, aggregationId: null }
    const projectItems = groups.value.find((group) => group.id === 'project')?.items
    expect(projectItems?.map((item) => [item.id, item.current, item.to])).toEqual([
      ['projectMembers', true, { name: 'projectMembers', params: { projectId: 'project-a' } }],
    ])
    expect(groups.value.some((group) => group.id === 'evaluation')).toBe(false)
  })

  it('does not derive membership management from an operator project role', async () => {
    const { groups, project } = await navigationAt('projectOverview', 'operator')
    project.value = { ...project.value!, currentUserCanManageMembers: false }
    expect(
      groups.value.flatMap((group) => group.items).some((item) => item.id === 'projectMembers'),
    ).toBe(false)
  })

  it('uses stable task entry without requiring a selected snapshot or run', async () => {
    const { groups, project } = await navigationAt('projectOverview')
    project.value = { ...project.value!, snapshotId: null, runId: null, aggregationId: null }
    const taskItems = groups.value
      .flatMap((group) => group.items)
      .filter((item) => ['classification', 'review', 'game', 'people'].includes(item.id))
    expect(taskItems.map((item) => [item.id, item.to])).toEqual([
      ['classification', { name: 'projectClassification', params: { projectId: 'project-a' } }],
      ['review', { name: 'projectReview', params: { projectId: 'project-a' } }],
      ['people', { name: 'projectAnnotation', params: { projectId: 'project-a' } }],
      ['game', { name: 'projectGame', params: { projectId: 'project-a' } }],
    ])
    expect(groups.value.some((group) => group.id === 'evaluation')).toBe(false)
    expect(groups.value.flatMap((group) => group.items).every((item) => item.to !== null)).toBe(
      true,
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
      'projects',
      'overview',
      'projectMembers',
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
