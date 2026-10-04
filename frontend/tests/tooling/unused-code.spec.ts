import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

const FRONTEND_ROOT = join(import.meta.dirname, '../..')
const frontendPackage = JSON.parse(readFileSync(join(FRONTEND_ROOT, 'package.json'), 'utf8')) as {
  scripts: { 'unused:check': string }
  dependencies: Record<string, string>
  devDependencies: Record<string, string>
}
const fixtures: string[] = []

type AnalyzerIssue = {
  file: string
  files: { name: string }[]
  exports: { name: string }[]
  types: { name: string }[]
  unresolved: { name: string }[]
}

afterEach(() => {
  for (const fixture of fixtures.splice(0)) rmSync(fixture, { recursive: true, force: true })
})

function createFixture(): string {
  const root = mkdtempSync(join(tmpdir(), 'gendertagger-knip-'))
  fixtures.push(root)
  // Resolve the real pinned analyzer and Vue plugin dependencies without a fixture installation.
  symlinkSync(join(FRONTEND_ROOT, 'node_modules'), join(root, 'node_modules'), 'dir')
  const files: Record<string, string> = {
    'package.json': JSON.stringify({
      name: 'application-reachability-regression',
      private: true,
      type: 'module',
      scripts: { 'unused:check': frontendPackage.scripts['unused:check'], test: 'vitest run' },
      dependencies: { vue: frontendPackage.dependencies.vue },
      devDependencies: {
        knip: frontendPackage.devDependencies.knip,
        vite: frontendPackage.devDependencies.vite,
        vitest: frontendPackage.devDependencies.vitest,
      },
    }),
    'knip.jsonc': readFileSync(join(FRONTEND_ROOT, 'knip.jsonc'), 'utf8'),
    'tsconfig.json': JSON.stringify({
      compilerOptions: { moduleResolution: 'bundler', paths: { '@/*': ['./src/*'] } },
      include: ['src/**/*'],
    }),
    'src/main.ts': `import { createApp } from 'vue'
import App from './App.vue'
import { routes } from './router'
import { unrelated } from './unrelated'
createApp(App).provide('routes', routes).mount('#app')
console.log(unrelated())
`,
    'src/App.vue': `<script setup lang="ts">
import TemplateChild from '@/TemplateChild.vue'
import DynamicChild from './DynamicChild.vue'
import { templateLabel } from './labels'
import type { LiveProps } from './types'
const props = defineProps<LiveProps>()
const model = defineModel<string>()
const dynamic = DynamicChild
</script>
<template>
  <TemplateChild :label="templateLabel" />
  <component :is="dynamic" />
  <p>{{ props.label }} {{ model }}</p>
</template>
`,
    'src/TemplateChild.vue': `<script setup lang="ts">
defineProps<{ label: string }>()
</script>
<template><span>{{ label }}</span></template>
`,
    'src/DynamicChild.vue': '<template><span>Dynamic component</span></template>\n',
    'src/router.ts': `export const routes = [{ path: '/lazy', component: () => import('./LazyView.vue') }]
`,
    'src/LazyView.vue': `<script setup lang="ts">
import LazyChild from './LazyChild.vue'
</script>
<template><LazyChild /></template>
`,
    'src/LazyChild.vue': '<template><span>Lazy child</span></template>\n',
    'src/labels.ts': `export const templateLabel = 'Template consumer'
`,
    'src/types.ts': `import type { GeneratedResponse } from './api/schema'
import type { OrdinaryDeclaration } from './ordinary'
export type LiveProps = { label: string; response?: GeneratedResponse; ordinary?: OrdinaryDeclaration }
export type TestOnlyAlias = { dead: true }
export const testOnlyValue = 'Not part of the application'
`,
    'src/api/schema.d.ts': `export interface GeneratedResponse { id: string }
export type UnusedGeneratedEndpoint = { serverOnly: true }
`,
    'src/ordinary.d.ts': `export interface OrdinaryDeclaration { id: string }
export type UnusedOrdinaryAlias = { dead: true }
`,
    'src/TestOnly.vue': '<template><span>Test-only orphan</span></template>\n',
    'src/ToolOnly.vue': '<template><span>Tool-only orphan</span></template>\n',
    'tests/orphan.spec.ts': `import TestOnly from '../src/TestOnly.vue'
import { testOnlyValue, type TestOnlyAlias } from '../src/types'
export const testConsumer: TestOnlyAlias = { dead: true }
console.log(TestOnly, testOnlyValue)
`,
    'scripts/tool.ts': `import ToolOnly from '../src/ToolOnly.vue'
console.log(ToolOnly)
`,
    // Same spelling in an unrelated live scope is not an export reference.
    'src/unrelated.ts': `export const unrelated = () => {
  type TestOnlyAlias = string
  const value: TestOnlyAlias = 'unrelated local alias'
  return value
}
`,
  }
  for (const [path, content] of Object.entries(files)) {
    const target = join(root, path)
    mkdirSync(dirname(target), { recursive: true })
    writeFileSync(target, content)
  }
  return root
}

function analyze(root: string): { status: number | null; issues: AnalyzerIssue[] } {
  const result = spawnSync('npm', ['run', '--silent', 'unused:check', '--', '--reporter', 'json'], {
    cwd: root,
    encoding: 'utf8',
    timeout: 15_000,
    env: { ...process.env, NO_COLOR: '1' },
  })
  expect(result.error, result.stderr).toBeUndefined()
  expect([0, 1], result.stderr).toContain(result.status)
  const report = JSON.parse(result.stdout) as { issues: AnalyzerIssue[] }
  return { status: result.status, issues: report.issues }
}

describe('production application reachability', () => {
  it('reports test/tool-only Vue orphans and unconsumed exports, not real application edges', () => {
    const result = analyze(createFixture())

    expect(result.status).toBe(1)
    expect(
      result.issues
        .filter((issue) => issue.files.length > 0)
        .map((issue) => issue.file)
        .sort(),
    ).toEqual(['src/TestOnly.vue', 'src/ToolOnly.vue'])
    const aliases = result.issues.flatMap((issue) =>
      issue.types.map((type) => [issue.file, type.name]),
    )
    expect(aliases).toEqual(
      expect.arrayContaining([
        ['src/types.ts', 'TestOnlyAlias'],
        ['src/ordinary.d.ts', 'UnusedOrdinaryAlias'],
      ]),
    )
    expect(aliases).toHaveLength(2)
    expect(result.issues.flatMap((issue) => issue.exports.map((value) => value.name))).toEqual([
      'testOnlyValue',
    ])
    expect(result.issues.flatMap((issue) => issue.unresolved)).toEqual([])
    expect(result.issues.map((issue) => issue.file).sort()).toEqual([
      'src/TestOnly.vue',
      'src/ToolOnly.vue',
      'src/ordinary.d.ts',
      'src/types.ts',
    ])
  })

  it('passes after orphan removal and keeping internally used aliases private', () => {
    const root = createFixture()
    rmSync(join(root, 'src/TestOnly.vue'))
    rmSync(join(root, 'src/ToolOnly.vue'))
    writeFileSync(
      join(root, 'src/types.ts'),
      `import type { GeneratedResponse } from './api/schema'
import type { OrdinaryDeclaration } from './ordinary'
type PrivateLabel = string
export type LiveProps = { label: PrivateLabel; response?: GeneratedResponse; ordinary?: OrdinaryDeclaration }
`,
    )
    writeFileSync(
      join(root, 'src/ordinary.d.ts'),
      'export interface OrdinaryDeclaration { id: string }\n',
    )

    expect(analyze(root)).toEqual({ status: 0, issues: [] })
  })
})
