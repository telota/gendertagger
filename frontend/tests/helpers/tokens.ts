import { readFileSync } from 'node:fs'
import { join } from 'node:path'

export type TokenMap = ReadonlyMap<string, string>
export type ThemeName = 'light' | 'dark'

const STYLES_DIRECTORY = join(import.meta.dirname, '../../src/styles')

export const DARK_SELECTOR = ":root[data-theme='dark']"

/** Read a stylesheet from `src/styles/` with comments removed. */
export function readStylesheet(name: string): string {
  return readFileSync(join(STYLES_DIRECTORY, name), 'utf-8').replace(/\/\*[\s\S]*?\*\//g, '')
}

/** Collect the custom properties declared by every rule whose selector is exactly `selector`. */
export function parseTokens(css: string, selector: string): TokenMap {
  const tokens = new Map<string, string>()
  const rule = /([^{}]+){([^{}]*)}/g
  for (const match of css.matchAll(rule)) {
    if (match[1]?.trim() !== selector) continue
    for (const declaration of (match[2] ?? '').matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
      const name = declaration[1]
      const value = declaration[2]
      if (name !== undefined && value !== undefined) tokens.set(name, value.trim())
    }
  }
  return tokens
}

/** Resolved tokens per theme: the dark theme overrides the light defaults. */
export function loadThemes(): Record<ThemeName, TokenMap> {
  const css = readStylesheet('tokens.css')
  const light = parseTokens(css, ':root')
  const dark = new Map([...light, ...parseTokens(css, DARK_SELECTOR)])
  return { light, dark }
}
