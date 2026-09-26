import { DOMWrapper, flushPromises } from '@vue/test-utils'
import axe from 'axe-core'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { AppLocale } from '@/app/i18n'

import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'
import {
  AGG_ID,
  catalogues,
  item,
  newServer,
  PROJECT_ID,
  reviewClient,
  RUN_ID,
  SNAPSHOT_ID,
  type Server,
} from './fixtures'

afterEach(() => {
  vi.restoreAllMocks()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('review decisions in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].review
  const base = `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/review`

  async function mountDecision(server: Server) {
    const wrapper = await mountApplicationAt(base, locale, reviewClient(server))
    await waitFor(() => expect(wrapper.find('.detail-history').exists()).toBe(true))
    await waitFor(() => expect(wrapper.find('.decision').exists()).toBe(true))
    await flushPromises()
    return wrapper
  }

  const keydown = (key: string, target: EventTarget = window) =>
    target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))

  it('offers no form without the reviewer role', async () => {
    const wrapper = await mountDecision(newServer({ role: 'viewer' }))

    expect(wrapper.find('.decision-form').exists()).toBe(false)
    expect(wrapper.get('.decision-muted').text()).toBe(messages.decision.viewerNote)
  })

  it('appends a correction against the revision the reviewer saw, then shows the new final label', async () => {
    const server = newServer()
    const wrapper = await mountDecision(server)

    await wrapper.get('#decision-correct-female').setValue(true)
    await wrapper.get('#decision-comment').setValue('  Attested in the register.  ')
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))

    expect(server.posts[0]).toEqual({
      snapshot_id: SNAPSHOT_ID,
      tei_id: 'demo-1',
      action: 'correct',
      label: 'female',
      comment: 'Attested in the register.',
      aggregated_result_id: 'r-demo-1',
      expected_revision: 2,
    })
    await waitFor(() => expect(wrapper.get('.decision-saved').text()).toContain('female'))
    // The chain grew by one and the queue's final label followed the decision ...
    await waitFor(() => expect(wrapper.findAll('.detail-history-entry')).toHaveLength(3))
    await waitFor(() => expect(wrapper.get('.row').text()).toContain('female'))
    // ... while the machine label the decision was made against is still what the machine said.
    const facts = wrapper.get('.detail-facts').text()
    expect(facts).toContain('male')
  })

  it('retains newer input and its focus when an earlier decision finishes saving', async () => {
    let resolveSave!: () => void
    const gate = new Promise<void>((resolve) => {
      resolveSave = resolve
    })
    const server = newServer({ gate })
    const wrapper = await mountDecision(server)
    await wrapper.get('#decision-correct-female').setValue(true)
    await wrapper.get('#decision-comment').setValue('Submitted reasoning')
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))
    await wrapper.get('#decision-correct-unknown').setValue(true)
    const comment = wrapper.get<HTMLTextAreaElement>('#decision-comment')
    await comment.setValue('A newer unsaved thought')
    comment.element.focus()

    resolveSave()
    await waitFor(() => expect(wrapper.get('.decision-saved').text()).toContain('female'))
    expect(wrapper.get<HTMLInputElement>('#decision-correct-unknown').element.checked).toBe(true)
    expect(comment.element.value).toBe('A newer unsaved thought')
    expect(document.activeElement).toBe(comment.element)
    expect(server.posts).toHaveLength(1)
    expect(server.posts[0]).toMatchObject({ label: 'female', comment: 'Submitted reasoning' })

    const leaving = wrapper.vm.$router.push('/')
    await waitFor(() =>
      expect(new DOMWrapper(document.body).find('[role="dialog"]').exists()).toBe(true),
    )
    const stay = new DOMWrapper(document.body)
      .get('[role="dialog"]')
      .findAll('button')
      .find((button) => button.text() === catalogues[locale].draftNavigation.stay)
    await stay?.trigger('click')
    await leaving
    expect(comment.element.value).toBe('A newer unsaved thought')
    wrapper.unmount()
  })

  it.each(['ok', 'conflict'] as const)(
    'keeps the leave dialog in control of focus after a pending %s response',
    async (postOutcome) => {
      let resolveSave!: () => void
      const gate = new Promise<void>((resolve) => {
        resolveSave = resolve
      })
      const server = newServer({ gate, postOutcome })
      const wrapper = await mountDecision(server)
      await wrapper.get('#decision-correct-female').setValue(true)
      await wrapper.get('#decision-comment').setValue('Submitted reasoning')
      await wrapper.get('.decision-form').trigger('submit')
      await waitFor(() => expect(server.posts).toHaveLength(1))

      const leaving = wrapper.vm.$router.push('/')
      await waitFor(() =>
        expect(new DOMWrapper(document.body).find('[role="dialog"]').exists()).toBe(true),
      )
      const dialog = new DOMWrapper(document.body).get('[role="dialog"]')
      await waitFor(() => expect(dialog.element.contains(document.activeElement)).toBe(true))
      const focused = document.activeElement
      const focus = vi.spyOn(HTMLElement.prototype, 'focus')
      resolveSave()
      await waitFor(() => {
        if (postOutcome === 'ok') expect(wrapper.get('.decision-saved').text()).toContain('female')
        else expect(wrapper.find('.decision-conflict').exists()).toBe(true)
      })
      expect(document.activeElement).toBe(focused)
      expect(focus.mock.contexts).not.toContain(
        wrapper.get(postOutcome === 'ok' ? '.decision-saved' : '.decision-conflict').element,
      )
      expect(wrapper.vm.$router.currentRoute.value.path).toBe(base)
      const stay = dialog
        .findAll('button')
        .find((button) => button.text() === catalogues[locale].draftNavigation.stay)
      await stay?.trigger('click')
      await leaving
      wrapper.unmount()
    },
  )

  it('only ever writes annotations: nothing else is created, changed or removed', async () => {
    const server = newServer()
    const wrapper = await mountDecision(server)

    await wrapper.get('#decision-correct-unknown').setValue(true)
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))
    await flushPromises()

    expect(server.writes).toEqual(['POST /api/v1/annotations'])
  })

  it('confirms the machine label by sending exactly that label', async () => {
    const server = newServer()
    const wrapper = await mountDecision(server)

    await wrapper.get('#decision-verify').setValue(true)
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))

    expect(server.posts[0]).toMatchObject({ action: 'verify', label: 'male' })
  })

  it('defers without a label', async () => {
    const server = newServer()
    const wrapper = await mountDecision(server)

    await wrapper.get('#decision-defer').setValue(true)
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))

    expect(server.posts[0]).toMatchObject({ action: 'defer' })
    expect(server.posts[0]).not.toHaveProperty('label')
    expect(server.posts[0]).not.toHaveProperty('comment')
  })

  it('cannot confirm a machine label that does not exist', async () => {
    const server = newServer({
      pages: [{ items: [item('demo-1', { machine_label: null, final_label: null })], next: null }],
    })
    const wrapper = await mountDecision(server)

    expect(wrapper.get('#decision-verify').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.decision-choices').text()).toContain(messages.decision.noMachineLabel)
  })

  it('does not save without a choice', async () => {
    const server = newServer()
    const wrapper = await mountDecision(server)

    expect(wrapper.get('#decision-save').attributes('disabled')).toBeDefined()
    await wrapper.get('.decision-form').trigger('submit')
    await flushPromises()

    expect(server.posts).toHaveLength(0)
  })

  it('chooses the label with the keys 1 to 4 and moves to the save button, so Enter saves', async () => {
    const server = newServer()
    const wrapper = await mountDecision(server)

    keydown('3')
    await flushPromises()

    expect((wrapper.get('#decision-correct-unknown').element as HTMLInputElement).checked).toBe(
      true,
    )
    expect(document.activeElement).toBe(wrapper.get('#decision-save').element)
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(1))
    expect(server.posts[0]).toMatchObject({ action: 'correct', label: 'unknown' })
  })

  it('leaves the number keys alone while text is being typed', async () => {
    const wrapper = await mountDecision(newServer())
    const comment = wrapper.get('#decision-comment').element as HTMLTextAreaElement
    comment.focus()

    keydown('2', comment)
    await flushPromises()

    expect((wrapper.get('#decision-correct-female').element as HTMLInputElement).checked).toBe(
      false,
    )
    expect(wrapper.get('#decision-save').attributes('disabled')).toBeDefined()
  })

  it('keeps the optional comment collapsed until the reviewer opens it', async () => {
    const wrapper = await mountDecision(newServer())
    const disclosure = wrapper.get('.decision-comment-disclosure')

    expect(disclosure.attributes('open')).toBeUndefined()
    expect(disclosure.get('summary').text()).toBe(messages.decision.comment)
    expect(wrapper.get('#decision-comment').attributes('aria-labelledby')).toBe(
      'decision-comment-summary',
    )

    await disclosure.get('summary').trigger('click')
    expect(disclosure.attributes('open')).toBe('')
  })

  it('lists the keys next to the labels and says how to save', async () => {
    const wrapper = await mountDecision(newServer())

    const keys = wrapper.findAll('.decision-key').map((k) => k.text())
    expect(keys).toEqual(['1', '2', '3', '4'])
    for (const [index, key] of wrapper.findAll('kbd').entries()) {
      const label = key.element.closest('label')
      expect(label?.textContent).toContain(
        messages.decision.key.replace('{key}', String(index + 1)),
      )
      expect(key.attributes('aria-label')).toBeUndefined()
      expect(key.attributes('aria-hidden')).toBe('true')
    }
    // Axe reported this defect as incomplete rather than a violation in the original audit.
    const result = await axe.run(wrapper.get('.decision').element, {
      runOnly: { type: 'rule', values: ['aria-prohibited-attr'] },
    })
    expect(result.violations).toEqual([])
    expect(result.incomplete).toEqual([])
    expect(wrapper.text()).toContain(messages.decision.keyboardHint)
    expect(wrapper.findAll('.decision .vocab-gloss')).toHaveLength(0)
  })

  it('turns a stale write into a designed recovery, not a lost or overwritten decision', async () => {
    const server = newServer({ postOutcome: 'conflict' })
    const wrapper = await mountDecision(server)

    await wrapper.get('#decision-correct-female').setValue(true)
    await wrapper.get('#decision-comment').setValue('My reasoning')
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.decision-conflict').exists()).toBe(true))

    // Announced and focused, naming who changed the person and what they decided.
    const box = wrapper.get('.decision-conflict')
    expect(box.attributes('role')).toBe('alert')
    expect(document.activeElement).toBe(box.element)
    await waitFor(() =>
      expect(wrapper.get('.decision-conflict-latest').text()).toContain('Alex Other'),
    )
    // The chain was re-read, so the reviewer can see what happened.
    await waitFor(() => expect(wrapper.findAll('.detail-history-entry')).toHaveLength(3))
    expect(wrapper.get('.decision-save').attributes('disabled')).toBeDefined()

    // Deciding again keeps the comment, drops the stale choice, and writes against the new revision.
    await wrapper.get('.decision-decide-again').trigger('click')
    expect(wrapper.find('.decision-conflict').exists()).toBe(false)
    expect((wrapper.get('#decision-comment').element as HTMLTextAreaElement).value).toBe(
      'My reasoning',
    )
    expect((wrapper.get('#decision-correct-female').element as HTMLInputElement).checked).toBe(
      false,
    )

    server.postOutcome = 'ok'
    await wrapper.get('#decision-correct-female').setValue(true)
    await waitFor(() =>
      expect(wrapper.get('#decision-save').attributes('disabled')).toBeUndefined(),
    )
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(server.posts).toHaveLength(2))

    expect(server.posts[0]).toMatchObject({ expected_revision: 2 })
    expect(server.posts[1]).toMatchObject({ expected_revision: 3, comment: 'My reasoning' })
  })

  it('can discard the input after a conflict', async () => {
    const server = newServer({ postOutcome: 'conflict' })
    const wrapper = await mountDecision(server)

    await wrapper.get('#decision-correct-female').setValue(true)
    await wrapper.get('#decision-comment').setValue('Discard me')
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.decision-conflict').exists()).toBe(true))

    await wrapper.get('.decision-discard').trigger('click')

    expect(wrapper.find('.decision-conflict').exists()).toBe(false)
    expect((wrapper.get('#decision-comment').element as HTMLTextAreaElement).value).toBe('')
  })

  it('says so when the server refuses the reviewer', async () => {
    const server = newServer({ postOutcome: 'forbidden' })
    const wrapper = await mountDecision(server)

    await wrapper.get('#decision-defer').setValue(true)
    await wrapper.get('.decision-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.decision-error').exists()).toBe(true))

    expect(wrapper.get('.decision-error').text()).toBe(messages.decision.errors.forbidden)
    expect(wrapper.find('.decision-conflict').exists()).toBe(false)
  })

  it('starts the next person with a clean form after discarding the current draft', async () => {
    const wrapper = await mountDecision(newServer())
    await wrapper.get('#decision-correct-female').setValue(true)
    await wrapper.get('#decision-comment').setValue('for demo-1')

    await wrapper.findAll('button.row')[1]?.trigger('click')
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
    const discard = Array.from(
      document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'),
    ).find((button) => button.textContent?.trim() === catalogues[locale].draftNavigation.discard)
    expect(discard).toBeDefined()
    discard?.click()
    await waitFor(() => expect(wrapper.get('.detail-name').text()).toContain('demo-2'))

    expect((wrapper.get('#decision-correct-female').element as HTMLInputElement).checked).toBe(
      false,
    )
    expect((wrapper.get('#decision-comment').element as HTMLTextAreaElement).value).toBe('')
  })
})
