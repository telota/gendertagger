import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * jsdom lays nothing out, so a screen that forgets its page padding passes every other test and then
 * sits flush against the sidebar and the window edge (found in a real browser at M9). The app shell
 * does not pad; each routed screen pads its own <main>, so each must say so.
 */
const SRC = join(__dirname, '../../src/features')

function views(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return views(path)
    return path.endsWith('View.vue') ? [path] : []
  })
}

const ROUTED = views(SRC).filter((path) => /<main class="/.test(readFileSync(path, 'utf8')))

describe('routed screens', () => {
  it('finds the screens', () => {
    expect(ROUTED.length).toBeGreaterThan(15)
  })

  it.each(ROUTED.map((path) => [path.slice(SRC.length + 1), path]))(
    '%s pads its own <main>',
    (_name, path) => {
      const source = readFileSync(path as string, 'utf8')
      const root = /<main class="([a-z0-9-]+)"/.exec(source)?.[1]
      expect(root).toBeTruthy()
      const rule = new RegExp(`\\.${root as string} \\{[^}]*\\}`).exec(source)?.[0] ?? ''

      expect(rule).toMatch(/padding:/)
    },
  )
})
