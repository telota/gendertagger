import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

const FEATURES = join(import.meta.dirname, '../../src/features')

const CREATION_ACTION_ROWS = [
  {
    path: 'projects/ProjectCreationForm.vue',
    rowClass: 'project-creation-actions',
    action: /class="project-creation-submit"/,
  },
  {
    path: 'runs/NewRunForm.vue',
    rowClass: 'app-form-actions',
    action: /class="new-run-submit"/,
  },
  {
    path: 'evaluation/NewEvaluationForm.vue',
    rowClass: 'app-form-actions',
    action: /class="new-evaluation-submit"/,
  },
  {
    path: 'export/NewExportForm.vue',
    rowClass: 'app-form-actions',
    action: /class="new-export-submit"/,
  },
  {
    path: 'admin/AdminUserCreationForm.vue',
    rowClass: 'admin-user-creation-actions',
    action: /type="submit" :disabled="isSubmitting"/,
  },
  {
    path: 'admin/AdminTeamsView.vue',
    rowClass: 'app-form-actions',
    action: /type="submit" :disabled="mutations\.isMutating\.value"/,
  },
  {
    path: 'projects/ProjectMembershipView.vue',
    rowClass: 'project-members-add-actions',
    action: /@click="addMember"/,
  },
  {
    path: 'projects/SnapshotImportForm.vue',
    rowClass: 'import-actions',
    action: /class="import-submit"/,
  },
] as const

const CREATION_TOGGLES = [
  ['projects/ProjectListView.vue', 'project-creation-panel', 'creationOpen'],
  ['runs/RunListView.vue', 'new-classification-panel', 'formOpen'],
  ['evaluation/EvaluationListView.vue', 'new-evaluation-panel', 'formOpen'],
  ['export/ExportListView.vue', 'new-export-panel', 'formOpen'],
  ['admin/AdminUserDirectoryView.vue', 'admin-user-creation-panel', 'creationOpen'],
  ['admin/AdminTeamsView.vue', 'admin-team-creation-panel', 'creationOpen'],
  ['projects/ProjectMembershipView.vue', 'project-member-add-panel', 'addMemberOpen'],
  ['projects/ProjectOverviewView.vue', 'project-import-panel', 'importOpen'],
] as const

describe('top creation form actions', () => {
  it.each(CREATION_ACTION_ROWS)(
    '$path keeps its commit action in the shared trailing row',
    ({ path, rowClass, action }) => {
      const source = readFileSync(join(FEATURES, path), 'utf8')
      const escaped = rowClass.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      const rowStart = [
        ...source.matchAll(/<div\b[^>]*class="([^"]*\bapp-form-actions\b[^"]*)"[^>]*>/g),
      ].find((match) => match[1]?.split(/\s+/).includes(rowClass))

      expect(rowStart, `${path} is missing its shared action row`).toBeDefined()
      const actionRegion = source.slice(rowStart?.index ?? 0, (rowStart?.index ?? 0) + 900)
      expect(actionRegion, `${path} leaves its commit action outside the shared row`).toMatch(
        action,
      )

      if (rowClass !== 'app-form-actions') {
        const localRule = new RegExp(`\\.${escaped}\\s*\\{([^}]*)\\}`).exec(source)?.[1] ?? ''
        expect(localRule, `${path} overrides the shared trailing-edge alignment`).not.toMatch(
          /justify-content\s*:/,
        )
      }
    },
  )

  it.each(CREATION_TOGGLES)(
    '%s keeps its disclosure trigger in the heading actions with consistent emphasis',
    (path, controls, openState) => {
      const source = readFileSync(join(FEATURES, path), 'utf8')
      const control = `aria-controls="${controls}"`
      const controlIndex = source.indexOf(control)
      expect(controlIndex, `${path} is missing ${control}`).toBeGreaterThanOrEqual(0)

      const triggerRegion = source.slice(Math.max(0, controlIndex - 700), controlIndex + 200)
      expect(triggerRegion).toContain('app-page-heading__actions')
      expect(triggerRegion).toContain(`:variant="${openState} ? 'ghost' : 'solid'"`)
    },
  )

  it('keeps secondary member-loading before the trailing Add action', () => {
    const source = readFileSync(join(FEATURES, 'projects/ProjectMembershipView.vue'), 'utf8')
    const rowStart = source.indexOf('class="project-members-add-actions app-form-actions"')
    const rowEnd = source.indexOf('</div>', rowStart)
    const row = source.slice(rowStart, rowEnd)

    expect(row.indexOf('@click="management.candidates.fetchNextPage()"')).toBeLessThan(
      row.indexOf('@click="addMember"'),
    )
    expect(source).not.toContain('.project-members-add > div')
  })
})
