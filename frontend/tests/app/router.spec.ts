import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'

import { createAppRouter, routes } from '@/app/router'

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
    ['/irgendwas', 'notFound'],
    ['/impressum/zu-viel', 'notFound'],
  ])('resolves %s to %s', async (path, name) => {
    expect((await resolve(path)).name).toBe(name)
  })

  it('names every route so links never depend on a path string', () => {
    expect(routes.every((route) => typeof route.name === 'string')).toBe(true)
  })

  it('loads the lazy views on demand', async () => {
    for (const path of ['/impressum', '/irgendwas']) {
      const { matched } = await resolve(path)
      expect(matched[0]?.components?.default).toBeDefined()
    }
  })
})
