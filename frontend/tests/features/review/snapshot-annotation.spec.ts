import { flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { expectNoAxeViolations } from '../../helpers/axe'
import { mountApplicationAt } from '../../helpers/render'
import {
  OTHER_SNAPSHOT,
  PROJECT,
  SNAPSHOT,
  person,
  snapshot,
  taskClient,
  taskServer,
} from '../../helpers/taskFixtures'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en }
const mounted: VueWrapper[] = []
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)(
  'snapshot annotation without classification in %s',
  (locale) => {
    const messages = catalogues[locale]
    const basePath = `/projects/${PROJECT}/snapshots/${SNAPSHOT}/annotations`
    async function mount(
      tei = 'demo-1',
      server = taskServer({ runPages: [[]], resultPages: [[]] }),
    ) {
      const wrapper = await mountApplicationAt(
        `${basePath}${tei ? `/${tei}` : ''}`,
        locale,
        taskClient(server),
      )
      mounted.push(wrapper)
      await waitFor(() => expect(wrapper.find('.snapshot-annotations').exists()).toBe(true))
      return { wrapper, server }
    }
    async function ready(wrapper: VueWrapper) {
      await waitFor(() => expect(wrapper.find('.annotation-detail').exists()).toBe(true))
      await waitFor(() =>
        expect(wrapper.get('.annotation-detail').text()).toContain(
          messages.review.detail.history.empty,
        ),
      )
    }

    it('appends the first human decision at revision zero without inventing model evidence', async () => {
      const { wrapper, server } = await mount()
      await ready(wrapper)
      await waitFor(() => expect(wrapper.findAll('.annotation-people li')).toHaveLength(1))
      expect(
        server.requests.find((r) => r.path.endsWith('/annotation-items'))?.query.has('q'),
      ).toBe(false)
      expect(wrapper.find('#decision-verify').exists()).toBe(false)
      expect(wrapper.get('.decision-subtitle').text()).toBe(messages.annotation.chooseLabel)
      expect(wrapper.find('.review-certainty, .review-predictions').exists()).toBe(false)
      await wrapper.get('#decision-correct-female').setValue(true)
      await wrapper.get('#decision-comment').setValue(' Attested in the source. ')
      await wrapper.get('.decision-form').trigger('submit')
      await waitFor(() => expect(server.posts).toHaveLength(1))
      expect(server.posts[0]).toEqual({
        snapshot_id: SNAPSHOT,
        tei_id: 'demo-1',
        action: 'correct',
        label: 'female',
        comment: 'Attested in the source.',
        expected_revision: 0,
      })
      expect(server.posts[0]).not.toHaveProperty('aggregated_result_id')
      await waitFor(() => expect(wrapper.get('.decision-saved').text()).toContain('female'))
      await waitFor(() => expect(wrapper.get('.annotation-current').text()).toContain('female'))
      expect(wrapper.get('.annotation-history-disclosure ol').text()).toContain(
        'Attested in the source.',
      )
      expect(
        server.requests.some((r) => /\/runs(?:\/|$)|\/aggregations(?:\/|$)/.test(r.path)),
      ).toBe(false)
      expect(server.writes).toEqual(['POST /api/v1/annotations'])
    })

    it('loads a deep-linked person outside the loaded page without replacing the selection', async () => {
      const { wrapper, server } = await mount(
        'later-person',
        taskServer({
          peoplePages: [[person()], [person('second-page')]],
          knownPeople: [person(), person('second-page'), person('later-person')],
        }),
      )
      await ready(wrapper)
      expect(wrapper.get('.annotation-detail header code').text()).toBe('later-person')
      expect(wrapper.findAll('.annotation-people li')).toHaveLength(1)
      expect(wrapper.get('.annotation-people').text()).not.toContain('later-person')
      expect(server.requests.some((r) => r.path.endsWith('/annotation-items/later-person'))).toBe(
        true,
      )
      const more = wrapper
        .findAll('.annotation-register button')
        .find((b) => b.text() === messages.annotation.more)!
      await more.trigger('click')
      await waitFor(() => expect(wrapper.findAll('.annotation-people li')).toHaveLength(2))
      expect(wrapper.get('.annotation-detail header code').text()).toBe('later-person')
      expect(wrapper.vm.$router.currentRoute.value.params.teiId).toBe('later-person')
      expect(
        server.requests
          .find((r) => r.path.endsWith('/annotation-items') && r.query.has('cursor'))
          ?.query.get('cursor'),
      ).toBe('page-1')
    })

    it('keeps raw records and annotation history readable for viewers without write controls', async () => {
      const { wrapper, server } = await mount('demo-1', taskServer({ role: 'viewer' }))
      await ready(wrapper)
      expect(wrapper.get('.decision').text()).toContain(messages.review.decision.viewerNote)
      expect(wrapper.find('.decision-form').exists()).toBe(false)
      expect(wrapper.findAll('.annotation-context a')).toHaveLength(0)
      expect(wrapper.get('.annotation-heading a').attributes('href')).toBe(
        `/projects/${PROJECT}/snapshots`,
      )
      window.dispatchEvent(new KeyboardEvent('keydown', { key: '1', bubbles: true }))
      await flushPromises()
      expect(server.posts).toEqual([])
      expect(server.writes).toEqual([])
    })

    it('submits search and decision filters to the server while retaining the selected person', async () => {
      const { wrapper, server } = await mount()
      await ready(wrapper)
      const before = server.requests.filter((r) => r.path.endsWith('/annotation-items')).length
      await wrapper.get('#annotation-search').setValue(' Ada ')
      await wrapper.get('#annotation-state').setValue('reviewed')
      await wrapper.get('#annotation-label').setValue('female')
      expect(server.requests.filter((r) => r.path.endsWith('/annotation-items'))).toHaveLength(
        before,
      )
      await wrapper.get('.annotation-filters').trigger('submit')
      await waitFor(() =>
        expect(
          server.requests.some(
            (r) => r.path.endsWith('/annotation-items') && r.query.get('q') === 'Ada',
          ),
        ).toBe(true),
      )
      const filtered = server.requests.find(
        (r) => r.path.endsWith('/annotation-items') && r.query.get('q') === 'Ada',
      )!
      expect(filtered.query.getAll('workflow_states')).toEqual(['reviewed'])
      expect(filtered.query.get('human_label')).toBe('female')
      expect(wrapper.vm.$router.currentRoute.value.params.teiId).toBe('demo-1')
      expect(wrapper.get('.annotation-detail header code').text()).toBe('demo-1')
    })

    it('reports collection failures as errors and retains a readable selected record', async () => {
      const { wrapper } = await mount(
        'demo-1',
        taskServer({ failures: new Set([`/api/v1/snapshots/${SNAPSHOT}/annotation-items`]) }),
      )
      await ready(wrapper)
      await waitFor(() =>
        expect(wrapper.get('.annotation-register').text()).toContain(messages.annotation.loadError),
      )
      expect(wrapper.get('.annotation-register').text()).not.toContain(messages.annotation.empty)
      expect(wrapper.find('.annotation-detail').exists()).toBe(true)
    })

    it('does not read annotation records for a snapshot belonging to another project', async () => {
      const { wrapper, server } = await mount(
        'demo-1',
        taskServer({
          snapshotOverrides: { [SNAPSHOT]: snapshot(SNAPSHOT, { project_id: 'another-project' }) },
        }),
      )
      await waitFor(() =>
        expect(wrapper.get('.snapshot-annotations').text()).toContain(
          messages.taskEntry.selectionUnavailable,
        ),
      )
      expect(wrapper.find('.annotation-detail').exists()).toBe(false)
      expect(server.requests.some((r) => r.path.includes('/annotation-items'))).toBe(false)
      expect(server.writes).toEqual([])
    })

    it.each(['picker', 'snapshot'] as const)(
      'protects a draft when changing to another %s',
      async (destination) => {
        const { wrapper } = await mount(
          'demo-1',
          taskServer({
            snapshotPages: [[snapshot(), snapshot(OTHER_SNAPSHOT)]],
            knownPeople: [person(), person('demo-1', { snapshot_id: OTHER_SNAPSHOT })],
          }),
        )
        await ready(wrapper)
        await wrapper.get('#decision-correct-female').setValue(true)
        await wrapper.get('#decision-comment').setValue('Keep this draft')
        const target =
          destination === 'picker'
            ? `/projects/${PROJECT}/annotation`
            : `/projects/${PROJECT}/snapshots/${OTHER_SNAPSHOT}/annotations/demo-1`
        let navigation = wrapper.vm.$router.push(target)
        await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
        const choice = (label: string) =>
          Array.from(document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')).find(
            (b) => b.textContent?.trim() === label,
          )!
        choice(messages.draftNavigation.stay).click()
        await navigation
        expect(wrapper.vm.$router.currentRoute.value.path).toBe(`${basePath}/demo-1`)
        expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element.value).toBe(
          'Keep this draft',
        )
        navigation = wrapper.vm.$router.push(target)
        await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
        choice(messages.draftNavigation.discard).click()
        await navigation
        expect(wrapper.vm.$router.currentRoute.value.path).toBe(target)
        if (destination === 'snapshot') {
          await ready(wrapper)
          expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element.value).toBe('')
          expect(wrapper.get<HTMLInputElement>('#decision-correct-female').element.checked).toBe(
            false,
          )
        }
      },
    )

    it('has accessible raw list, source details and decision controls', async () => {
      const { wrapper } = await mount()
      await ready(wrapper)
      await expectNoAxeViolations(wrapper.get('.snapshot-annotations').element)
    })
  },
)
