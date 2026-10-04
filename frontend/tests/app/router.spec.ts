import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'

import { createAppRouter } from '@/app/router'

async function resolve(path: string) {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  await router.isReady()
  return router.currentRoute.value
}

describe('routes', () => {
  it.each([
    ['/', 'home'],
    ['/impressum', 'legalNotice'],
    ['/login', 'login'],
    ['/change-password', 'changePassword'],
    ['/admin/users', 'adminUsers'],
    ['/settings', 'userSettings'],
    ['/projects/project-a/snapshots', 'projectSnapshots'],
    ['/projects/project-a/snapshots/snapshot-a', 'snapshotDetail'],
    ['/projects/project-a/snapshots/snapshot-a/runs', 'snapshotRuns'],
    ['/projects/project-a/snapshots/snapshot-a/runs/run-a', 'runDetail'],
    ['/projects/project-a/game', 'projectGame'],
    ['/projects/project-a/runs/run-a/aggregations/aggregation-a/game', 'game'],
    [
      '/projects/project-a/snapshots/snapshot-a/runs/run-a/executions/execution-a/results',
      'methodExecutionResults',
    ],
    ['/irgendwas', 'notFound'],
    ['/impressum/zu-viel', 'notFound'],
  ])('resolves %s to %s', async (path, name) => {
    expect((await resolve(path)).name).toBe(name)
  })

  it('loads the lazy views on demand', async () => {
    for (const path of ['/impressum', '/irgendwas']) {
      const { matched } = await resolve(path)
      expect(matched[0]?.components?.default).toBeDefined()
    }
  })
})
