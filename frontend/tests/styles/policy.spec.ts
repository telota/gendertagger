import { readdirSync, readFileSync, statSync } from 'node:fs'
import { extname, join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

// docs/26-frontend-coding-guidelines.md, "Styling": colours, spacing and type come from tokens, and a
// few CSS constructs are prohibited outright.

const SOURCE_ROOT = join(import.meta.dirname, '../../src')
const TOKENS_FILE = join(SOURCE_ROOT, 'styles', 'tokens.css')

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? sourceFiles(path) : [path]
  })
}

/** The CSS a file contributes: whole stylesheets, and the `<style>` blocks of components. */
function styleText(path: string): string {
  const content = readFileSync(path, 'utf-8')
  if (extname(path) === '.css') return content
  if (extname(path) === '.vue') {
    return [...content.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join('\n')
  }
  return ''
}

const styleSources = sourceFiles(SOURCE_ROOT)
  .map((path) => ({
    file: relative(SOURCE_ROOT, path).replaceAll('\\', '/'),
    css: styleText(path).replace(/\/\*[\s\S]*?\*\//g, ''),
  }))
  .filter(({ css }) => css.trim() !== '')

const styled = styleSources.filter(({ file }) => file !== 'styles/tokens.css')

function defaultRootCustomProperties(css: string): Set<string> {
  const properties = new Set<string>()
  let depth = 0
  let selectorStart = 0
  let rootBodyStart: number | undefined

  for (let index = 0; index < css.length; index += 1) {
    if (css[index] === '{') {
      if (depth === 0 && css.slice(selectorStart, index).trim() === ':root') {
        rootBodyStart = index + 1
      }
      depth += 1
      continue
    }
    if (css[index] !== '}') continue

    depth -= 1
    if (depth !== 0) continue
    if (rootBodyStart !== undefined) {
      const body = css.slice(rootBodyStart, index)
      for (const match of body.matchAll(/(?:^|;)\s*(--[\w-]+)\s*:/g)) {
        if (match[1] !== undefined) properties.add(match[1])
      }
      rootBodyStart = undefined
    }
    selectorStart = index + 1
  }

  return properties
}

function unguardedCustomPropertyReferences(css: string): string[] {
  return [...css.matchAll(/var\(\s*(--[\w-]+)\s*(,|\))/g)]
    .filter((match) => match[2] === ')')
    .map((match) => match[1])
    .filter((name): name is string => name !== undefined)
}

const RULES: readonly (readonly [string, RegExp])[] = [
  ['a raw hex colour', /#[0-9a-f]{3,8}\b/i],
  ['a raw rgb()/hsl() colour', /\b(?:rgba?|hsla?)\(/i],
  ['!important', /!important/i],
  ['a px font size', /font-size\s*:\s*[\d.]+px/i],
  ['filter: invert()', /invert\(/i],
]

describe('style policy', () => {
  it('finds the stylesheets it is meant to police', () => {
    expect(styled.map(({ file }) => file)).toContain('app/App.vue')
  })

  it.each(RULES)('no component or stylesheet uses %s outside the token layer', (_name, pattern) => {
    const offenders = styled.filter(({ css }) => pattern.test(css)).map(({ file }) => file)
    expect(offenders).toEqual([])
  })

  it('uses a default root token for every custom property reference without a fallback', () => {
    const tokenCss = styleText(TOKENS_FILE).replace(/\/\*[\s\S]*?\*\//g, '')
    const globalTokens = defaultRootCustomProperties(tokenCss)
    const offenders = styleSources.flatMap(({ file, css }) => {
      return unguardedCustomPropertyReferences(css)
        .filter((name) => !globalTokens.has(name))
        .map((name) => `${file}: ${name}`)
    })

    expect([...new Set(offenders)].sort()).toEqual([])
  })

  it('does not mistake conditional declarations or guarded extension properties for root tokens', () => {
    const tokens = defaultRootCustomProperties(`
      :root { --always: 1; }
      @media (width < 10px) { :root { --conditional: 1; } }
    `)

    expect([...tokens]).toEqual(['--always'])
    expect(unguardedCustomPropertyReferences('color: var(--missing)')).toEqual(['--missing'])
    expect(unguardedCustomPropertyReferences('color: var(--extension, var(--always))')).toEqual([
      '--always',
    ])
  })
})
