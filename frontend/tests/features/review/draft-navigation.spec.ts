import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'

import { createAppRouter } from '@/app/router'
import en from '@/locales/en.json'

import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'
import { AGG_ID, newServer, PROJECT_ID, reviewClient, RUN_ID } from './fixtures'

afterEach(() => document.body.replaceChildren())

const base = `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/review`

function dialogButton(label: string): HTMLButtonElement {
  const button = Array.from(
    document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'),
  ).find((candidate) => candidate.textContent?.trim() === label)
  if (!button) throw new Error(`No dialog button ${label}`)
  return button
}

describe('review draft navigation registration', () => {
  it('retains the decision across filters and cancelled navigation, and ignores shortcuts in the prompt', async () => {
    const router = createAppRouter(createMemoryHistory())
    const server = newServer()
    const wrapper = await mountApplicationAt(base, 'en', reviewClient(server), router)
    try {
      await waitFor(() => expect(wrapper.find('#decision-correct-female').exists()).toBe(true))
      await wrapper.get('#decision-correct-female').setValue(true)
      await wrapper.get('#decision-comment').setValue('Still checking the source')
      await router.push({ query: { ...router.currentRoute.value.query, q: 'Surname' } })
      await flushPromises()
      expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element.value).toBe(
        'Still checking the source',
      )
      expect(document.querySelector('[role="dialog"]')).toBeNull()

      const navigation = router.push('/projects')
      await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
      window.dispatchEvent(new KeyboardEvent('keydown', { key: '1', bubbles: true }))
      await flushPromises()
      expect(wrapper.get<HTMLInputElement>('#decision-correct-female').element.checked).toBe(true)
      dialogButton(en.draftNavigation.stay).click()
      await navigation
      expect(router.currentRoute.value.path).toBe(base)
      expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element.value).toBe(
        'Still checking the source',
      )
      expect(server.posts).toHaveLength(0)
    } finally {
      wrapper.unmount()
    }
  })

  it('allows leaving after a successful save without prompting again', async () => {
    const router = createAppRouter(createMemoryHistory())
    const server = newServer()
    const wrapper = await mountApplicationAt(base, 'en', reviewClient(server), router)
    try {
      await waitFor(() => expect(wrapper.find('#decision-correct-female').exists()).toBe(true))
      await wrapper.get('#decision-correct-female').setValue(true)
      await wrapper.get('.decision-form').trigger('submit')
      await waitFor(() => expect(wrapper.get('.decision-saved').text()).toContain('female'))
      await router.push('/projects')
      expect(router.currentRoute.value.path).toBe('/projects')
      expect(document.querySelector('[role="dialog"]')).toBeNull()
      expect(server.posts).toHaveLength(1)
    } finally {
      wrapper.unmount()
    }
  })
})
