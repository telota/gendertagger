import { mount } from '@vue/test-utils'
import { defineComponent, reactive, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createAppI18n } from '@/app/i18n'
import { routes } from '@/app/router'
import { useSidebarNavigation } from '@/app/useSidebarNavigation'
import type { ProjectNavigationContext } from '@/app/useProjectNavigation'
import en from '@/locales/en.json'

const state = vi.hoisted(() => ({ project: undefined as unknown, access: undefined as unknown }))
vi.mock('@/app/useProjectNavigation', () => ({ useProjectNavigation: () => state.project }))
vi.mock('@/composables/useAdminAccess', () => ({ useAdminAccess: () => state.access }))

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
  })
  const session = reactive({ canUsePrivateNavigation: true })
  state.project = project
  state.access = { session, canAccessAdmin: ref(true) }
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
  return { groups, project, session }
}

describe('sidebar route ownership', () => {
  it.each([
    ['projects', 'projects'],
    ['projectOverview', 'overview'],
    ['projectMembers', 'overview'],
    ['projectImport', 'import'],
    ['snapshotRuns', 'classification'],
    ['runDetail', 'classification'],
    ['aggregationDetail', 'classification'],
    ['review', 'review'],
    ['people', 'people'],
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

  it('describes missing prerequisites without constructing invalid targets', async () => {
    const { groups, project } = await navigationAt('projectOverview')
    project.value = { ...project.value!, snapshotId: null, runId: null, aggregationId: null }
    const unavailable = groups.value
      .flatMap((group) => group.items)
      .filter((item) => item.to === null)
    expect(unavailable.map((item) => [item.id, item.unavailableReason])).toEqual([
      ['classification', en.nav.requiresSnapshot],
      ['review', en.nav.requiresAggregation],
      ['people', en.nav.requiresAggregation],
      ['evaluations', en.nav.requiresRun],
      ['exports', en.nav.requiresRun],
    ])
  })

  it('hides ineligible destinations instead of offering disabled role-restricted items', async () => {
    const { groups, session } = await navigationAt('people', 'viewer')
    const ids = groups.value.flatMap((group) => group.items).map((item) => item.id)
    expect(ids).not.toContain('import')
    expect(ids).not.toContain('review')
    expect(ids).toContain('people')
    expect(ids).toContain('exports')
    session.canUsePrivateNavigation = false
    expect(groups.value).toEqual([])
  })
})
