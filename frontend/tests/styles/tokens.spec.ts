import { describe, expect, it } from 'vitest'

import { contrastRatio } from '../helpers/contrast'
import {
  DARK_SELECTOR,
  loadThemes,
  parseTokens,
  readStylesheet,
  type ThemeName,
} from '../helpers/tokens'

const themes = loadThemes()
const LABELS = ['male', 'female', 'institution', 'unknown'] as const

function colour(theme: ThemeName, token: string): string {
  const value = themes[theme].get(`--${token}`)
  if (value === undefined) throw new Error(`--${token} is not defined in the ${theme} theme`)
  return value
}

function ratio(theme: ThemeName, foreground: string, background: string): number {
  return contrastRatio(colour(theme, foreground), colour(theme, background))
}

describe('theme completeness', () => {
  const css = readStylesheet('tokens.css')
  // Matches anywhere in the value, not just at the start, so a compound value that merely contains
  // a colour (a box-shadow's `rgba(...)`) still counts as theme-scoped.
  const containsColour = (value: string): boolean => /#|rgba?\(|hsla?\(/.test(value)
  const lightColours = [...parseTokens(css, ':root')]
    .filter(([, value]) => containsColour(value))
    .map(([name]) => name)
    .sort()
  const darkColours = [...parseTokens(css, DARK_SELECTOR).keys()]
    .filter((name) => lightColours.includes(name))
    .sort()

  it('defines every colour token in both themes', () => {
    expect(darkColours).toEqual(lightColours)
  })

  it('does not define anything in the dark theme that the light theme lacks', () => {
    const darkOnly = [...parseTokens(css, DARK_SELECTOR).keys()].filter(
      (name) => !lightColours.includes(name),
    )
    expect(darkOnly).toEqual([])
  })

  it('gives every canonical label a solid, a text and a tint token', () => {
    for (const label of LABELS) {
      for (const suffix of ['', '-text', '-tint']) {
        expect(lightColours).toContain(`--${label}${suffix}`)
      }
    }
  })

  it('names the fourth label group after the label, not the tier', () => {
    expect(lightColours.some((name) => name.startsWith('--uncertain'))).toBe(false)
  })
})

describe.each(['light', 'dark'] as const)('contrast in the %s theme', (theme) => {
  it.each([
    ['text-primary', 'page', 4.5],
    ['text-primary', 'panel', 4.5],
    ['text-secondary', 'page', 4.5],
    ['text-secondary', 'panel', 4.5],
    ['muted', 'page', 4.5],
    ['muted', 'panel', 4.5],
    ['accent', 'panel', 4.5],
    ['accent-b', 'panel', 4.5],
    ['critical-text', 'page', 4.5],
    ['critical-text', 'panel', 4.5],
    ['critical-text', 'surface-1', 4.5],
    // Filled destructive buttons keep the panel foreground on the critical solid.
    ['panel', 'critical', 4.5],
    ['focus-ring', 'page', 3],
    ['focus-ring', 'panel', 3],
  ] as const)('%s on %s reaches %s:1', (foreground, background, minimum) => {
    expect(ratio(theme, foreground, background)).toBeGreaterThanOrEqual(minimum)
  })

  it.each(LABELS)('%s text on its own tint meets AA for text', (label) => {
    expect(ratio(theme, `${label}-text`, `${label}-tint`)).toBeGreaterThanOrEqual(4.5)
  })
})

// The measured values published in docs/25-frontend-design-guidelines.md. A palette refinement has
// to update the document and this table together, so an unverified change cannot slip through.
describe('documented measurements', () => {
  it.each([
    ['light', 'text-primary', 'page', 17.43],
    ['light', 'text-secondary', 'panel', 7.94],
    ['light', 'muted', 'page', 4.51],
    ['light', 'muted', 'panel', 5.1],
    ['light', 'accent', 'panel', 8.56],
    ['light', 'accent-b', 'panel', 5.27],
    ['light', 'critical-text', 'page', 4.98],
    ['light', 'critical-text', 'panel', 5.62],
    ['light', 'critical-text', 'surface-1', 5.47],
    ['light', 'panel', 'critical', 4.8],
    ['light', 'focus-ring', 'page', 6.14],
    ['light', 'male-text', 'male-tint', 6.08],
    ['light', 'female-text', 'female-tint', 4.72],
    ['light', 'institution-text', 'institution-tint', 4.82],
    ['light', 'unknown-text', 'unknown-tint', 5.95],
    ['dark', 'text-primary', 'page', 15.83],
    ['dark', 'text-primary', 'panel', 14.32],
    ['dark', 'text-secondary', 'panel', 8.66],
    ['dark', 'muted', 'panel', 5.53],
    ['dark', 'accent', 'panel', 6.54],
    ['dark', 'accent-b', 'panel', 7.12],
    ['dark', 'critical-text', 'page', 6.18],
    ['dark', 'critical-text', 'panel', 5.59],
    ['dark', 'critical-text', 'surface-1', 5.03],
    ['dark', 'panel', 'critical', 5.59],
    ['dark', 'warning', 'panel', 8.81],
    ['dark', 'good', 'panel', 7.42],
    ['dark', 'focus-ring', 'page', 8.96],
  ] as const)('%s: %s on %s measures %s', (theme, foreground, background, expected) => {
    expect(ratio(theme, foreground, background)).toBeCloseTo(expected, 2)
  })
})

describe('scales', () => {
  const scales = themes.light

  it('declares type sizes in rem so the reader font setting applies', () => {
    const sizes = [...scales].filter(([name]) => name.startsWith('--font-size-'))
    expect(sizes.length).toBeGreaterThan(0)
    for (const [name, value] of sizes) expect(value, name).toMatch(/^[\d.]+rem$/)
  })

  it('keeps state transitions under 150 ms', () => {
    expect(Number.parseInt(scales.get('--motion-state') ?? '', 10)).toBeLessThan(150)
  })
})
