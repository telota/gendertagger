// Fail on message-catalogue drift between locales (decision D3, docs/26-frontend-coding-guidelines.md).
//
// Checks that every locale defines exactly the same keys, that no message is empty, and that each key
// uses the same named placeholders in every locale. Unused and undefined keys are covered by the
// @intlify/vue-i18n rules that run as part of `npm run lint`.

import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const LOCALE_DIRECTORY = fileURLToPath(new URL('../src/locales/', import.meta.url))
const PLACEHOLDER = /\{(\w+)\}/g

function flatten(node, prefix = '') {
  const entries = new Map()
  for (const [key, value] of Object.entries(node)) {
    const path = prefix === '' ? key : `${prefix}.${key}`
    if (typeof value === 'string') {
      entries.set(path, value)
    } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      for (const [nested, message] of flatten(value, path)) entries.set(nested, message)
    } else {
      throw new Error(`${path}: catalogue values must be strings or nested objects`)
    }
  }
  return entries
}

function placeholders(message) {
  return [...message.matchAll(PLACEHOLDER)].map((match) => match[1]).sort()
}

const files = (await readdir(LOCALE_DIRECTORY)).filter((name) => name.endsWith('.json')).sort()
const catalogues = new Map()
for (const file of files) {
  const parsed = JSON.parse(await readFile(join(LOCALE_DIRECTORY, file), 'utf-8'))
  catalogues.set(file.replace(/\.json$/, ''), flatten(parsed))
}

const problems = []
const allKeys = new Set([...catalogues.values()].flatMap((entries) => [...entries.keys()]))

for (const [locale, entries] of catalogues) {
  for (const key of [...allKeys].sort()) {
    const message = entries.get(key)
    if (message === undefined) {
      problems.push(`${locale}: missing key ${key}`)
      continue
    }
    if (message.trim() === '') problems.push(`${locale}: empty message for ${key}`)
    for (const [otherLocale, otherEntries] of catalogues) {
      const other = otherEntries.get(key)
      if (other === undefined || otherLocale <= locale) continue
      if (placeholders(message).join() !== placeholders(other).join()) {
        problems.push(`${key}: placeholders differ between ${locale} and ${otherLocale}`)
      }
    }
  }
}

if (problems.length > 0) {
  console.error(problems.join('\n'))
  process.exit(1)
}
console.log(`Message catalogues agree: ${catalogues.size} locales, ${allKeys.size} keys.`)
