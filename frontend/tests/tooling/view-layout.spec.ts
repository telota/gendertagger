import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * jsdom lays nothing out, so a screen that forgets its page padding passes every other test and then
 * sits flush against the sidebar and the window edge (found in a real browser at M9). The app shell
 * does not pad: every page owner uses the shared frame and one named width modifier only when its
 * task calls for an intentional exception to the standard 60rem measure.
 */
const SRC = join(__dirname, '../../src/features')
const LAYOUT_CSS = readFileSync(join(__dirname, '../../src/styles/layout.css'), 'utf8')
const SHARED_FRAME_RULE = /\.app-page-frame\s*\{[^}]*\}/.exec(LAYOUT_CSS)?.[0] ?? ''
const DENSE_FRAME_RULE = /\.app-page-frame--dense\s*\{[^}]*\}/.exec(LAYOUT_CSS)?.[0] ?? ''

function vueFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return vueFiles(path)
    return path.endsWith('.vue') ? [path] : []
  })
}

const PAGE_OWNERS = vueFiles(SRC).filter((path) => /<main\b/.test(readFileSync(path, 'utf8')))
const DENSE_PAGE_OWNERS = new Set([
  'review/ReviewWorkbench.vue',
  'review/SnapshotAnnotationView.vue',
])
const READING_PAGE_OWNERS = new Set([
  'errors/NotFoundView.vue',
  'home/HomeView.vue',
  'legal/LegalNoticeView.vue',
])
const AUTH_PAGE_OWNERS = new Set(['auth/ChangePasswordView.vue', 'auth/LoginView.vue'])
const FORM_PAGE_OWNERS = new Set(['settings/UserSettingsView.vue'])
const WIDE_PAGE_OWNERS = new Set(['runs/MethodExecutionResultsView.vue'])
const PAGE_FRAME_MODIFIERS = [
  ['app-page-frame--reading', READING_PAGE_OWNERS],
  ['app-page-frame--auth', AUTH_PAGE_OWNERS],
  ['app-page-frame--form', FORM_PAGE_OWNERS],
  ['app-page-frame--wide', WIDE_PAGE_OWNERS],
  ['app-page-frame--dense', DENSE_PAGE_OWNERS],
] as const

const RECIPE_ADOPTION = [
  [
    'runs/AggregationDetailView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-fact-list',
      'app-fact-list__item',
      'app-card',
    ],
  ],
  ['runs/AggregationItem.vue', ['app-fact-list', 'app-fact-list__item', 'app-resource-card']],
  ['runs/RunProvenance.vue', ['app-fact-list', 'app-fact-list__item', 'app-card']],
  [
    'evaluation/EvaluationListView.vue',
    ['app-page-frame', 'app-page-heading', 'app-page-heading__title', 'app-card'],
  ],
  [
    'evaluation/EvaluationDetailView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-fact-list',
      'app-fact-list__item',
      'app-card',
    ],
  ],
  [
    'export/ExportListView.vue',
    ['app-page-frame', 'app-page-heading', 'app-page-heading__title', 'app-card'],
  ],
  [
    'export/ExportDetailView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-fact-list',
      'app-fact-list__item',
      'app-card',
    ],
  ],
  [
    'admin/AdminSettingsView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-fact-list',
      'app-fact-list__item',
      'app-card',
      'app-card--sectioned',
    ],
  ],
  ['admin/AdminSettingsEditor.vue', ['app-card', 'app-card--sectioned']],
  [
    'admin/AdminUserDirectoryView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
      'app-card--sectioned',
    ],
  ],
  ['admin/AdminUserCreationForm.vue', ['app-card']],
  [
    'admin/AdminTeamsView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
      'app-card--sectioned',
      'app-resource-card',
    ],
  ],
  [
    'tasks/ProjectTaskView.vue',
    ['app-page-frame', 'app-page-heading', 'app-page-heading__title', 'app-resource-card'],
  ],
  [
    'runs/RunListView.vue',
    ['app-page-frame', 'app-page-heading', 'app-page-heading__title', 'app-card'],
  ],
  [
    'runs/RunDetailView.vue',
    ['app-page-frame', 'app-page-heading', 'app-page-heading__title', 'app-card'],
  ],
  [
    'runs/MethodExecutionResultsView.vue',
    [
      'app-page-frame',
      'app-page-frame--wide',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
    ],
  ],
  ['runs/ExecutionCard.vue', ['app-fact-list', 'app-fact-list__item', 'app-resource-card']],
  [
    'projects/ProjectListView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
      'app-resource-card',
    ],
  ],
  [
    'projects/ProjectMembershipView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
      'app-card--sectioned',
    ],
  ],
  [
    'projects/SnapshotDetailView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-fact-list',
      'app-fact-list__item',
      'app-card',
      'app-card--sectioned',
    ],
  ],
  ['projects/SnapshotRecordPanel.vue', ['app-resource-card']],
  ['projects/SnapshotRecords.vue', ['app-card', 'app-card--sectioned']],
  ['projects/SnapshotList.vue', ['app-card', 'app-resource-card']],
  ['projects/SnapshotImportForm.vue', ['app-card']],
  ['projects/ProjectCreationForm.vue', ['app-card', 'app-multiline-field']],
  ['projects/ImportView.vue', ['app-page-frame', 'app-page-heading', 'app-page-heading__title']],
  [
    'projects/ProjectSnapshotsView.vue',
    ['app-page-frame', 'app-page-heading', 'app-page-heading__title'],
  ],
  [
    'projects/ProjectOverviewView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
      'app-card--sectioned',
    ],
  ],
  ['projects/SnapshotStatisticsPanel.vue', ['app-card']],
  ['evaluation/AccuracyTable.vue', ['app-card']],
  ['evaluation/CoverageTable.vue', ['app-card']],
  ['evaluation/ConfusionMatrices.vue', ['app-card']],
  ['evaluation/KappaMatrix.vue', ['app-card']],
  ['evaluation/EnsemblePanel.vue', ['app-card']],
  ['review/ReviewWorkbench.vue', ['app-page-frame', 'app-page-heading', 'app-page-heading__title']],
  [
    'review/SnapshotAnnotationView.vue',
    ['app-page-frame', 'app-page-heading', 'app-page-heading__title'],
  ],
  [
    'settings/UserSettingsView.vue',
    [
      'app-page-frame',
      'app-page-frame--form',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
      'app-card--sectioned',
    ],
  ],
  [
    'auth/LoginView.vue',
    [
      'app-page-frame',
      'app-page-frame--auth',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
    ],
  ],
  [
    'auth/ChangePasswordView.vue',
    [
      'app-page-frame',
      'app-page-frame--auth',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
    ],
  ],
  ['home/HomeView.vue', ['app-page-frame', 'app-page-frame--reading']],
  [
    'home/GuestHomeView.vue',
    ['app-page-heading', 'app-page-heading__title', 'app-card', 'app-card--sectioned'],
  ],
  [
    'home/SignedInHomeView.vue',
    ['app-page-heading', 'app-page-heading__title', 'app-card', 'app-card--sectioned'],
  ],
  [
    'legal/LegalNoticeView.vue',
    [
      'app-page-frame',
      'app-page-frame--reading',
      'app-page-heading',
      'app-page-heading__title',
      'app-fact-list',
      'app-fact-list__item',
      'app-card',
      'app-card--sectioned',
    ],
  ],
  [
    'errors/NotFoundView.vue',
    [
      'app-page-frame',
      'app-page-frame--reading',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
    ],
  ],
  [
    'game/GameModeView.vue',
    [
      'app-page-frame',
      'app-page-heading',
      'app-page-heading__title',
      'app-card',
      'app-card--sectioned',
    ],
  ],
] as const

describe('page frames', () => {
  it('finds the screens', () => {
    expect(PAGE_OWNERS.length).toBeGreaterThan(20)
  })

  it('defines the standard and dense shared insets', () => {
    expect(SHARED_FRAME_RULE).toMatch(/padding:\s*var\(--space-8\) var\(--page-gutter\)/)
    expect(DENSE_FRAME_RULE).toMatch(/padding-block:\s*var\(--space-4\)/)
  })

  it.each(PAGE_OWNERS.map((path) => [path.slice(SRC.length + 1), path]))(
    '%s delegates its outer geometry to the shared frame',
    (name, path) => {
      const relativePath = String(name)
      const source = readFileSync(path as string, 'utf8')
      const main = /<main\b[^>]*>/.exec(source)?.[0] ?? ''
      const staticClasses = /(?:^|\s)class="([^"]+)"/.exec(main)?.[1]?.split(/\s+/) ?? []
      const dynamicClasses = [...main.matchAll(/'([a-z][a-z0-9-]*)'/g)].map((match) => match[1])
      const classes = new Set([...staticClasses, ...dynamicClasses])

      expect(classes).toContain('app-page-frame')
      const expectedModifiers = PAGE_FRAME_MODIFIERS.filter(([, owners]) =>
        owners.has(relativePath),
      ).map(([modifier]) => modifier)
      const actualModifiers = PAGE_FRAME_MODIFIERS.map(([modifier]) => modifier).filter(
        (modifier) => classes.has(modifier),
      )

      expect(actualModifiers, `${relativePath} uses the wrong named page width`).toEqual(
        expectedModifiers,
      )

      for (const className of classes) {
        if (className?.startsWith('app-page-frame')) continue
        const escaped = className?.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') ?? ''
        const rules = [...source.matchAll(new RegExp(`\\.${escaped}\\s*\\{([^}]*)\\}`, 'g'))]

        for (const [, declarations = ''] of rules) {
          expect(
            declarations,
            `${relativePath} overrides page padding in .${className}`,
          ).not.toMatch(/padding(?:-(?:block|inline)(?:-(?:start|end))?)?\s*:/)
          expect(
            declarations,
            `${relativePath} overrides the shared page width in .${className}`,
          ).not.toMatch(/max-(?:inline-size|width)\s*:/)
          expect(
            declarations,
            `${relativePath} lets direct children shrink against the start edge in .${className}`,
          ).not.toMatch(/align-items\s*:\s*flex-start/)
        }
      }
    },
  )
})

describe('named layout recipe adoption', () => {
  it.each(RECIPE_ADOPTION)('%s keeps its agreed recipes', (relativePath, recipes) => {
    const source = readFileSync(join(SRC, relativePath), 'utf8')

    for (const recipe of recipes) {
      const escaped = recipe.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      const element = recipe.startsWith('app-page-frame')
        ? 'main'
        : recipe === 'app-page-heading'
          ? 'header'
          : recipe === 'app-page-heading__title'
            ? 'h1'
            : '[A-Za-z][A-Za-z0-9-]*'
      const use = recipe.startsWith('app-page-frame')
        ? new RegExp(`<${element}\\b[^>]*\\b${escaped}\\b[^>]*>`, 'i')
        : new RegExp(`<${element}[^>]*class="[^"]*\\b${escaped}\\b[^"]*"`, 'i')

      expect(source, `${relativePath} is missing ${recipe}`).toMatch(use)
    }
  })

  it('applies resource-card recipes to every repeated project and task card', () => {
    const projectList = readFileSync(join(SRC, 'projects/ProjectListView.vue'), 'utf8')
    const projectCards = [
      ...projectList.matchAll(/<li\b[^>]*class="([^"]*\bproject-card\b[^"]*)"/g),
    ]
    expect(projectCards).toHaveLength(2)
    for (const [, classes] of projectCards) {
      expect(classes).toMatch(/\bapp-resource-card\b/)
    }

    const projectTask = readFileSync(join(SRC, 'tasks/ProjectTaskView.vue'), 'utf8')
    const taskOptions = [...projectTask.matchAll(/<li\b[^>]*class="([^"]*\btask-option\b[^"]*)"/g)]
    expect(taskOptions).toHaveLength(4)
    for (const [, classes] of taskOptions) {
      expect(classes).toMatch(/\bapp-resource-card\b/)
    }
  })

  it('keeps one resource-card boundary per execution and config in a closed disclosure', () => {
    const source = readFileSync(join(SRC, 'runs/ExecutionCard.vue'), 'utf8')
    expect(source).toMatch(/<li\b[^>]*class="[^"]*\bexecution\b[^"]*\bapp-resource-card\b[^"]*"/)
    expect(source).toMatch(
      /<details\b[^>]*class="[^"]*\bexecution-provenance-config-disclosure\b[^"]*"/,
    )
    expect(source).not.toMatch(
      /<pre\b[^>]*class="[^"]*\bexecution-provenance-config\b[^"]*\bapp-resource-card\b/,
    )
  })

  it('keeps named cards on one standard inset without roomy variants', () => {
    const sources = vueFiles(SRC)
      .map((path) => readFileSync(path, 'utf8'))
      .join('\n')
    expect(sources).not.toContain('app-card--roomy')
    expect(sources).not.toContain('app-resource-card--roomy')
  })

  it('keeps the project description on the multiline-field recipe', () => {
    const source = readFileSync(join(SRC, 'projects/ProjectCreationForm.vue'), 'utf8')
    const textarea = /<textarea\b[^>]*id="project-create-description"[^>]*>/.exec(source)?.[0] ?? ''
    expect(textarea).toMatch(/class="[^"]*\bapp-multiline-field\b[^"]*"/)
  })
})
