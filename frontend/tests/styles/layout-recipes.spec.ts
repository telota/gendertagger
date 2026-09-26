import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const SOURCE_ROOT = join(import.meta.dirname, '../../src')
const layout = readFileSync(join(SOURCE_ROOT, 'styles/layout.css'), 'utf8')
const executionCard = readFileSync(join(SOURCE_ROOT, 'features/runs/ExecutionCard.vue'), 'utf8')
const snapshotRecordPanel = readFileSync(
  join(SOURCE_ROOT, 'features/projects/SnapshotRecordPanel.vue'),
  'utf8',
)
const CARD_RULE = /:is\(\.app-card, \.app-resource-card\)\s*\{([^}]*)\}/.exec(layout)?.[1] ?? ''

function rule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`${escaped}\\s*\\{([^}]*)\\}`).exec(layout)?.[1] ?? ''
}

describe('shared layout recipes', () => {
  it('defines the page frame and heading hierarchy', () => {
    expect(rule('.app-page-frame')).toContain('var(--page-gutter)')
    expect(rule('.app-page-frame')).toContain('max-inline-size: 60rem')
    expect(rule('.app-page-frame--reading')).toContain('max-inline-size: 40rem')
    expect(rule('.app-page-frame--auth')).toContain('max-inline-size: 24rem')
    expect(rule('.app-page-frame--form')).toContain('max-inline-size: 48rem')
    expect(rule('.app-page-frame--wide')).toContain('max-inline-size: 76rem')
    expect(rule('.app-page-frame--dense')).toContain('max-inline-size: none')
    expect(rule('.app-page-frame--dense')).toContain('padding-block: var(--space-4)')
    expect(rule('.app-page-heading')).toContain('flex-wrap: wrap')
    expect(rule('.app-page-heading__title')).toContain('var(--font-size-page)')
    expect(rule('.app-page-heading__description')).toContain('max-inline-size: 65ch')
    expect(rule('.app-page-heading__actions')).toContain('justify-content: flex-end')
    expect(rule('.app-form-actions')).toContain('grid-column: 1 / -1')
    expect(rule('.app-form-actions')).toContain('inline-size: 100%')
    expect(rule('.app-form-actions')).toContain('flex-wrap: wrap')
    expect(rule('.app-form-actions')).toContain('justify-content: flex-end')
  })

  it('defines responsive fact rows and one shared flat-card geometry', () => {
    expect(rule('.app-fact-list')).toContain('container: app-fact-list / inline-size')
    expect(rule('.app-fact-list__item')).toContain('minmax(0, 1fr)')
    expect(layout).toContain('@container app-fact-list (min-width: 24rem)')
    expect(CARD_RULE).toContain('padding: var(--app-card-padding, var(--space-4))')
    expect(CARD_RULE).toContain('border: 1px solid var(--border)')
    expect(CARD_RULE).toContain('background: var(--panel)')
    expect(rule('.app-card--sectioned')).toContain('--app-card-padding: 0')
    expect(layout).not.toContain('app-card--roomy')
    expect(layout).not.toContain('app-resource-card--roomy')
    expect(/\.execution--compact\s*\{[^}]*\}/.exec(executionCard)?.[0] ?? '').not.toMatch(/padding/)
    expect(snapshotRecordPanel).toContain("'app-resource-card': !embedded")
  })

  it('defines the multiline field and its invalid state', () => {
    expect(rule('.app-multiline-field')).toContain('border-radius: var(--radius-input)')
    expect(rule('.app-multiline-field')).toContain('resize: vertical')
    expect(rule(".app-multiline-field[aria-invalid='true']")).toContain(
      'border-color: var(--critical)',
    )
  })
})
