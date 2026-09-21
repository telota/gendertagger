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

const styled = sourceFiles(SOURCE_ROOT)
  .filter((path) => path !== TOKENS_FILE)
  .map((path) => ({
    file: relative(SOURCE_ROOT, path).replaceAll('\\', '/'),
    css: styleText(path).replace(/\/\*[\s\S]*?\*\//g, ''),
  }))
  .filter(({ css }) => css.trim() !== '')

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
})
