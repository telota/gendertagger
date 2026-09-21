import axe from 'axe-core'
import { expect } from 'vitest'

/**
 * Fail on any axe-core violation inside `element`.
 *
 * The colour-contrast rule is disabled because jsdom computes no layout or styles; contrast is asserted
 * against the tokens themselves in tests/styles/tokens.spec.ts, for both themes.
 */
export async function expectNoAxeViolations(element: Element): Promise<void> {
  const results = await axe.run(element, { rules: { 'color-contrast': { enabled: false } } })
  const summary = results.violations.map(
    (violation) => `${violation.id}: ${violation.nodes.map((node) => node.html).join(' | ')}`,
  )
  expect(summary).toEqual([])
}
