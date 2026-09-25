import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

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
  type Server,
} from './fixtures'

afterEach(() => {
  document.body.replaceChildren()
})

/** Four people with their own revisions; demo-3 has no machine label to confirm. */
function fourPeople(overrides: Partial<Server> = {}): Server {
  return newServer({
    pages: [
      {
        items: [
          item('demo-1', { review_revision: 2 }),
          item('demo-2', { review_revision: 3 }),
          item('demo-3', { review_revision: 0, machine_label: null, final_label: null }),
          item('demo-4', { review_revision: 1 }),
        ],
        next: null,
      },
    ],
    ...overrides,
  })
}

describe.each(['de', 'en'] as const)('bulk decisions in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].review
  const base = `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/review`

  async function mountBulk(server: Server) {
    const wrapper = await mountApplicationAt(base, locale, reviewClient(server))
    await waitFor(() => expect(wrapper.find('.row').exists()).toBe(true))
    await flushPromises()
    return wrapper
  }

  const tick = async (wrapper: Awaited<ReturnType<typeof mountBulk>>, ...indexes: number[]) => {
    for (const index of indexes) await wrapper.findAll('.row-check')[index]?.setValue(true)
  }

  it('offers no selection without the reviewer role', async () => {
    const wrapper = await mountBulk(fourPeople({ role: 'viewer' }))

    expect(wrapper.find('.bulk').exists()).toBe(false)
    expect(wrapper.find('.row-check').exists()).toBe(false)
  })

  it('selects one by one, all at once, and clears', async () => {
    const wrapper = await mountBulk(fourPeople())
    expect(wrapper.find('.bulk-form').exists()).toBe(false)

    await tick(wrapper, 0, 1)
    expect(wrapper.get('.bulk-count').text()).toMatch(/2/)
    expect(wrapper.find('.bulk-form').exists()).toBe(true)

    await wrapper.get('#bulk-all').setValue(true)
    expect(wrapper.get('.bulk-count').text()).toMatch(/4/)

    await wrapper.get('.bulk-clear').trigger('click')
    expect(wrapper.get('.bulk-count').text()).toBe('')
    expect(wrapper.find('.bulk-form').exists()).toBe(false)
  })

  it('asks for confirmation first and writes nothing until it is given', async () => {
    const server = fourPeople()
    const wrapper = await mountBulk(server)
    await tick(wrapper, 0, 1, 3)

    await wrapper.get('#bulk-action').setValue('correct:institution')
    await wrapper.get('.bulk-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.bulk-confirm').exists()).toBe(true))

    expect(wrapper.get('.bulk-confirm').text()).toContain('institution')
    expect(wrapper.get('.bulk-confirm').text()).toContain('Surname-demo-1')
    expect(document.activeElement).toBe(wrapper.get('.bulk-confirm').element)
    expect(server.posts).toHaveLength(0)

    await wrapper.get('.bulk-back').trigger('click')
    expect(wrapper.find('.bulk-confirm').exists()).toBe(false)
    expect(server.posts).toHaveLength(0)
  })

  it('saves one decision per person, in list order, each against its own revision', async () => {
    const server = fourPeople()
    const wrapper = await mountBulk(server)
    await tick(wrapper, 0, 1, 3)

    await wrapper.get('#bulk-action').setValue('correct:institution')
    await wrapper.get('#bulk-comment').setValue('Institutions, all three')
    await wrapper.get('.bulk-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.bulk-apply').exists()).toBe(true))
    await wrapper.get('.bulk-apply').trigger('click')
    await waitFor(() => expect(wrapper.find('.bulk-report').exists()).toBe(true))

    expect(server.posts.map((p) => [p.tei_id, p.expected_revision])).toEqual([
      ['demo-1', 2],
      ['demo-2', 3],
      ['demo-4', 1],
    ])
    for (const post of server.posts) {
      expect(post).toMatchObject({
        action: 'correct',
        label: 'institution',
        comment: 'Institutions, all three',
      })
    }
    expect(wrapper.get('.bulk-report-title').text()).toContain('3')
    expect(wrapper.findAll('.bulk-report-item--saved')).toHaveLength(3)
    // Saved people leave the selection, and only annotations were ever written.
    expect(wrapper.get('.bulk-count').text()).toBe('')
    expect(server.writes.every((w) => w === 'POST /api/v1/annotations')).toBe(true)
    // The queue was re-read once the run was over and shows the new final labels.
    await waitFor(() => expect(wrapper.get('.row').text()).toContain('institution'))
  })

  it('reports every person on its own when some fail, and keeps only those selected', async () => {
    const server = fourPeople({ conflictTeis: ['demo-2'], failTeis: ['demo-4'] })
    const wrapper = await mountBulk(server)
    await tick(wrapper, 0, 1, 3)

    await wrapper.get('#bulk-action').setValue('defer')
    await wrapper.get('.bulk-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.bulk-apply').exists()).toBe(true))
    await wrapper.get('.bulk-apply').trigger('click')
    await waitFor(() => expect(wrapper.find('.bulk-report').exists()).toBe(true))

    // Nobody's outcome hides another's; the conflict is not retried and the earlier write is not undone.
    expect(server.posts.map((p) => p.tei_id)).toEqual(['demo-1', 'demo-2', 'demo-4'])
    const items = wrapper.findAll('.bulk-report-item')
    expect(items.map((i) => i.classes().join(' '))).toEqual([
      expect.stringContaining('bulk-report-item--saved'),
      expect.stringContaining('bulk-report-item--conflict'),
      expect.stringContaining('bulk-report-item--failed'),
    ])
    expect(items[1]?.text()).toContain('9')
    expect(wrapper.get('.bulk-report-title').text()).toMatch(/1.*3/)
    expect(wrapper.get('.bulk-report').text()).toContain(messages.bulk.notSaved)
    // The two that were not saved stay selected for another try.
    expect(wrapper.get('.bulk-count').text()).toMatch(/2/)
    const ticked = wrapper.findAll('.row-check').map((c) => (c.element as HTMLInputElement).checked)
    expect(ticked).toEqual([false, true, false, true])
  })

  it('skips people without a machine label when confirming machine labels, and says so beforehand', async () => {
    const server = fourPeople()
    const wrapper = await mountBulk(server)
    await tick(wrapper, 0, 2)

    await wrapper.get('#bulk-action').setValue('verify')
    await wrapper.get('.bulk-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.bulk-confirm').exists()).toBe(true))
    expect(wrapper.get('.bulk-confirm').text()).toContain(
      messages.bulk.willSkip.replace('{count}', '1'),
    )
    await wrapper.get('.bulk-apply').trigger('click')
    await waitFor(() => expect(wrapper.find('.bulk-report').exists()).toBe(true))

    expect(server.posts).toHaveLength(1)
    expect(server.posts[0]).toMatchObject({ tei_id: 'demo-1', action: 'verify', label: 'male' })
    expect(wrapper.findAll('.bulk-report-item--skipped')).toHaveLength(1)
    expect(wrapper.get('.bulk-report-item--skipped').text()).toContain(
      messages.bulk.outcome.skipped,
    )
  })

  it('can be stopped: the person in flight is finished, the rest are not attempted', async () => {
    let release: () => void = () => {}
    const server = fourPeople({
      gate: new Promise<void>((resolve) => {
        release = resolve
      }),
    })
    const wrapper = await mountBulk(server)
    await tick(wrapper, 0, 1, 3)

    await wrapper.get('#bulk-action').setValue('defer')
    await wrapper.get('.bulk-form').trigger('submit')
    await waitFor(() => expect(wrapper.find('.bulk-apply').exists()).toBe(true))
    await wrapper.get('.bulk-apply').trigger('click')
    await waitFor(() => expect(server.posts).toHaveLength(1))
    expect(wrapper.get('.bulk-progress').text()).toMatch(/0.*3/)

    await wrapper.get('.bulk-stop').trigger('click')
    release()
    await waitFor(() => expect(wrapper.find('.bulk-report').exists()).toBe(true))

    expect(server.posts).toHaveLength(1)
    expect(wrapper.findAll('.bulk-report-item--saved')).toHaveLength(1)
    expect(wrapper.findAll('.bulk-report-item--notAttempted')).toHaveLength(2)
  })

  it('drops the selection when the list changes underneath it', async () => {
    const wrapper = await mountBulk(fourPeople())
    await tick(wrapper, 0, 1)
    expect(wrapper.get('.bulk-count').text()).toMatch(/2/)

    await wrapper.findAll('.queue')[1]?.trigger('click')
    await waitFor(() => expect(wrapper.get('.bulk-count').text()).toBe(''))
  })

  it('protects an unsubmitted choice and comment while Stay preserves the selection', async () => {
    const server = fourPeople()
    const wrapper = await mountBulk(server)
    await tick(wrapper, 0, 1)
    await wrapper.get('#bulk-action').setValue('defer')
    await wrapper.get('#bulk-comment').setValue('Check these sources first')
    const attempt = wrapper.vm.$router.push('/')
    await waitFor(() => expect(document.querySelector('.draft-leave-panel')).not.toBeNull())
    document.querySelector<HTMLButtonElement>('.draft-leave-actions button')!.click()
    await attempt
    expect(wrapper.vm.$route.path).toBe(base)
    expect((wrapper.get('#bulk-comment').element as HTMLTextAreaElement).value).toBe(
      'Check these sources first',
    )
    expect((wrapper.get('#bulk-action').element as HTMLSelectElement).value).toBe('defer')
    expect(wrapper.get('.bulk-count').text()).toMatch(/2/)
    expect(server.posts).toHaveLength(0)
    wrapper.unmount()
  })

  it('keeps a running sequence intact when the reviewer stays', async () => {
    let release!: () => void
    const server = fourPeople({
      gate: new Promise<void>((resolve) => {
        release = resolve
      }),
    })
    const wrapper = await mountBulk(server)
    await tick(wrapper, 0, 1)
    await wrapper.get('#bulk-action').setValue('defer')
    await wrapper.get('.bulk-form').trigger('submit')
    await wrapper.get('.bulk-apply').trigger('click')
    await waitFor(() => expect(server.posts).toHaveLength(1))
    const attempt = wrapper.vm.$router.push('/')
    await waitFor(() => expect(document.querySelector('.draft-leave-panel')).not.toBeNull())
    document.querySelector<HTMLButtonElement>('.draft-leave-actions button')!.click()
    await attempt
    expect(wrapper.vm.$route.path).toBe(base)
    release()
    await waitFor(() => expect(wrapper.findAll('.bulk-report-item--saved')).toHaveLength(2))
    expect(server.posts).toHaveLength(2)
    await wrapper.vm.$router.push('/')
    expect(document.querySelector('.draft-leave-panel')).toBeNull()
    wrapper.unmount()
  })

  it('finishes only the in-flight person after confirmed leave and never steals destination focus', async () => {
    let release!: () => void
    const server = fourPeople({
      gate: new Promise<void>((resolve) => {
        release = resolve
      }),
    })
    const wrapper = await mountBulk(server)
    await tick(wrapper, 0, 1, 3)
    await wrapper.get('#bulk-action').setValue('defer')
    await wrapper.get('.bulk-form').trigger('submit')
    await wrapper.get('.bulk-apply').trigger('click')
    await waitFor(() => expect(server.posts).toHaveLength(1))
    const attempt = wrapper.vm.$router.push('/')
    await waitFor(() => expect(document.querySelector('.draft-leave-panel')).not.toBeNull())
    document.querySelectorAll<HTMLButtonElement>('.draft-leave-actions button')[1]!.click()
    await attempt
    await waitFor(() => expect(document.activeElement).toBe(wrapper.get('#main-content').element))
    release()
    await flushPromises()
    await flushPromises()
    expect(server.posts.map((post) => post.tei_id)).toEqual(['demo-1'])
    expect(wrapper.vm.$route.path).toBe('/')
    expect(wrapper.find('.bulk-report').exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.get('#main-content').element)
    wrapper.unmount()
  })

  it('keeps focus in a pending leave dialog when submitted decisions finish', async () => {
    let release!: () => void
    const server = fourPeople({
      gate: new Promise<void>((resolve) => {
        release = resolve
      }),
    })
    const wrapper = await mountBulk(server)
    await tick(wrapper, 0, 1)
    await wrapper.get('#bulk-action').setValue('defer')
    await wrapper.get('.bulk-form').trigger('submit')
    await wrapper.get('.bulk-apply').trigger('click')
    await waitFor(() => expect(server.posts).toHaveLength(1))
    const attempt = wrapper.vm.$router.push('/')
    await waitFor(() =>
      expect(document.querySelector('.draft-leave-panel')?.contains(document.activeElement)).toBe(
        true,
      ),
    )
    release()
    await waitFor(() => expect(wrapper.findAll('.bulk-report-item--saved')).toHaveLength(2))
    expect(document.querySelector('.draft-leave-panel')?.contains(document.activeElement)).toBe(
      true,
    )
    document.querySelector<HTMLButtonElement>('.draft-leave-actions button')!.click()
    await attempt
    expect(wrapper.vm.$route.path).toBe(base)
    expect(wrapper.findAll('.bulk-report-item--saved')).toHaveLength(2)
    wrapper.unmount()
  })
})
