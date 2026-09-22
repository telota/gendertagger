import { describe, expect, it } from 'vitest'

import { SOURCE_CODE_LICENSE } from '@/app/publication'

describe('SOURCE_CODE_LICENSE', () => {
  it('links to the licence text over HTTPS', () => {
    expect(new URL(SOURCE_CODE_LICENSE.url).protocol).toBe('https:')
  })

  it('names a plausible licence, year and holder', () => {
    expect(SOURCE_CODE_LICENSE.name).toBe('MIT')
    expect(Number.isInteger(SOURCE_CODE_LICENSE.copyrightYear)).toBe(true)
    expect(SOURCE_CODE_LICENSE.copyrightHolder.length).toBeGreaterThan(0)
  })
})
