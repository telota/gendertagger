import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import { createAppI18n } from '@/app/i18n'
import { useRoleLabel } from '@/features/projects/useRoleLabel'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

const catalogues = { de, en } as const

function mountRoleLabel(locale: 'de' | 'en') {
  let roleLabel!: ReturnType<typeof useRoleLabel>
  mount(
    defineComponent({
      setup() {
        roleLabel = useRoleLabel()
        return () => null
      },
    }),
    { global: { plugins: [createAppI18n(locale)] } },
  )
  return roleLabel
}

describe.each(['de', 'en'] as const)('useRoleLabel in %s', (locale) => {
  const messages = catalogues[locale].projects.role

  it('translates every known project role', () => {
    const roleLabel = mountRoleLabel(locale)

    expect(roleLabel('viewer')).toBe(messages.viewer)
    expect(roleLabel('reviewer')).toBe(messages.reviewer)
    expect(roleLabel('operator')).toBe(messages.operator)
  })

  it('falls back to the raw value for an unrecognised role', () => {
    const roleLabel = mountRoleLabel(locale)

    expect(roleLabel('admin')).toBe('admin')
  })
})
