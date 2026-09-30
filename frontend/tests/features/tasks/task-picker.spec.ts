import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { expectNoAxeViolations } from '../../helpers/axe'
import { mountApplicationAt } from '../../helpers/render'
import {
  OTHER_RESULT,
  OTHER_RUN,
  OTHER_SNAPSHOT,
  PROJECT,
  RESULT,
  RUN,
  SNAPSHOT,
  result,
  run,
  snapshot,
  taskClient,
  taskServer,
} from '../../helpers/taskFixtures'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en }
const PROJECT_TASK_SOURCE = readFileSync(
  join(import.meta.dirname, '../../../src/features/tasks/ProjectTaskView.vue'),
  'utf8',
)
const mounted: VueWrapper[] = []
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  document.body.replaceChildren()
})

describe('task picker layout recipes', () => {
  it('cards every standalone feedback state with the shared recipe', () => {
    const template = PROJECT_TASK_SOURCE.split('</script>')[1]?.split('<style scoped>')[0] ?? ''
    const feedbackTags = [...template.matchAll(/<AppFeedback\b([^>]*)>/gs)]

    expect(feedbackTags.length).toBeGreaterThan(0)
    for (const [, attributes] of feedbackTags) {
      expect(attributes).toMatch(/class="[^"]*\bapp-card\b[^"]*"/)
    }
  })
})

describe.each(['de', 'en'] as const)('independent project picker in %s', (locale) => {
  const messages = catalogues[locale].taskEntry
  async function mount(path: string, server = taskServer()) {
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT}/${path}`,
      locale,
      taskClient(server),
    )
    mounted.push(wrapper)
    await waitFor(() => expect(wrapper.find('.task-entry').exists()).toBe(true))
    return { wrapper, server }
  }
  function button(wrapper: VueWrapper, label: string) {
    const found = wrapper.findAll('.task-entry button').find((entry) => entry.text() === label)
    if (!found) throw new Error(`Missing picker button ${label}`)
    return found
  }

  it('lists exact review results as cards across cursor pages', async () => {
    const server = taskServer({
      workingId: OTHER_RESULT,
      snapshotPages: [[snapshot(OTHER_SNAPSHOT)], [snapshot()]],
      runPages: [[run(OTHER_RUN)], [run()]],
      resultPages: [[result()], [result(OTHER_RESULT)]],
    })
    const { wrapper } = await mount('review', server)
    await waitFor(() => expect(wrapper.findAll('.task-option')).toHaveLength(1))
    expect(wrapper.vm.$router.currentRoute.value.query).toEqual({})
    expect(wrapper.vm.$router.currentRoute.value.name).toBe('projectReview')
    await button(wrapper, messages.moreResults).trigger('click')
    await waitFor(() => expect(wrapper.findAll('.task-option')).toHaveLength(2))
    const options = wrapper.findAll('.task-option')
    expect(options[0]!.get('a').attributes('href')).toContain(`/aggregations/${RESULT}/review`)
    expect(options[1]!.get('a').attributes('href')).toContain(
      `/aggregations/${OTHER_RESULT}/review`,
    )
    expect(options[0]!.find('.task-recommended').exists()).toBe(false)
    expect(options[1]!.get('.task-recommended').text()).toBe(messages.recommended)
    expect(server.writes).toEqual([])
    expect(server.workingId).toBe(OTHER_RESULT)
    const requests = server.requests
    expect(requests.find((r) => r.path.endsWith('/review-results'))?.query.get('limit')).toBe('25')
    expect(
      requests
        .filter((r) => r.path.endsWith('/review-results'))
        .at(-1)
        ?.query.get('cursor'),
    ).toBe('page-1')
    expect(
      requests.some(
        (r) => r.path.endsWith('/snapshots') && r.query.has('has_completed_aggregations'),
      ),
    ).toBe(false)
    expect(
      requests.some((r) => r.path.endsWith('/runs') && r.query.has('has_completed_aggregations')),
    ).toBe(false)
    expect(
      requests.some(
        (r) => r.path.endsWith('/aggregations') && r.query.get('status') === 'completed',
      ),
    ).toBe(false)
    await options[0]!.get('a').trigger('click')
    await waitFor(() =>
      expect(wrapper.vm.$router.currentRoute.value.params.aggregationId).toBe(RESULT),
    )
    expect(server.writes).toEqual([])
  })

  it('opens game mode from the same exact completed-result picker', async () => {
    const { wrapper, server } = await mount('game')
    await waitFor(() => expect(wrapper.findAll('.task-option')).toHaveLength(1))
    expect(wrapper.vm.$router.currentRoute.value.name).toBe('projectGame')
    const link = wrapper.get<HTMLAnchorElement>('.task-option a')
    expect(link.text()).toBe(messages.openGame)
    expect(link.attributes('href')).toContain(`/aggregations/${RESULT}/game`)
    expect(
      server.requests.some(
        (request) =>
          request.path.endsWith('/snapshots') ||
          request.path.endsWith('/runs') ||
          request.path.endsWith('/aggregations'),
      ),
    ).toBe(false)
    await expectNoAxeViolations(wrapper.get('.task-entry').element)
    await link.trigger('click')
    await waitFor(() => expect(wrapper.vm.$router.currentRoute.value.name).toBe('game'))
    expect(server.writes).toEqual([])
  })

  it('blocks the game picker when the project has disabled game mode', async () => {
    const { wrapper, server } = await mount('game', taskServer({ gameEnabled: false }))
    await waitFor(() =>
      expect(wrapper.get('.task-entry').text()).toContain(catalogues[locale].game.disabled),
    )
    expect(wrapper.find('.task-option').exists()).toBe(false)
    expect(wrapper.get('.task-entry > .app-feedback').classes()).toContain('app-card')
    expect(server.requests.some((request) => request.path.endsWith('/review-results'))).toBe(false)
  })

  it('lists completed results without a working pointer even when the overall run failed', async () => {
    const { wrapper, server } = await mount(
      `review?snapshot=${SNAPSHOT}&run=${RUN}`,
      taskServer({ runPages: [[run(RUN, { status: 'failed' })]] }),
    )
    await waitFor(() => expect(wrapper.findAll('.task-option')).toHaveLength(1))
    expect(wrapper.find('.task-recommended').exists()).toBe(false)
    expect(wrapper.vm.$router.currentRoute.value.name).toBe('projectReview')
    expect(server.writes).toEqual([])
    await expectNoAxeViolations(wrapper.get('.task-entry').element)
  })

  it.each(['snapshot', 'run'] as const)(
    'does not recommend a result whose %s identity does not match its ownership chain',
    async (mismatch) => {
      const server = taskServer({
        workingId: RESULT,
        ...(mismatch === 'snapshot'
          ? {
              snapshotPages: [[snapshot(OTHER_SNAPSHOT)]],
              snapshotOverrides: { [SNAPSHOT]: snapshot(OTHER_SNAPSHOT) },
            }
          : { runOverrides: { [RUN]: run(OTHER_RUN) } }),
      })
      const { wrapper } = await mount('review', server)
      await waitFor(() => expect(wrapper.findAll('.task-option')).toHaveLength(1))
      await flushPromises()
      expect(wrapper.find('.task-recommended').exists()).toBe(false)
      expect(wrapper.vm.$router.currentRoute.value.query).toEqual({})
      expect(server.writes).toEqual([])
    },
  )

  it('opens classification for the explicitly chosen snapshot', async () => {
    const { wrapper } = await mount('classification', taskServer({ role: 'viewer' }))
    await waitFor(() => expect(wrapper.findAll('.task-option')).toHaveLength(1))
    await wrapper.get('.task-option button').trigger('click')
    await waitFor(() => expect(wrapper.vm.$router.currentRoute.value.name).toBe('snapshotRuns'))
    expect(wrapper.vm.$router.currentRoute.value.params.snapshotId).toBe(SNAPSHOT)
  })

  it('focuses the next annotation step after its selected snapshot finishes loading', async () => {
    let resolveSnapshot!: () => void
    const snapshotGate = new Promise<void>((resolve) => {
      resolveSnapshot = resolve
    })
    const { wrapper, server } = await mount('annotation', taskServer({ snapshotGate }))
    await waitFor(() => expect(wrapper.find('.task-option button').exists()).toBe(true))
    wrapper.get<HTMLButtonElement>('.task-option button').element.focus()
    await wrapper.get('.task-option button').trigger('click')
    await waitFor(() =>
      expect(
        server.requests.some((request) => request.path === `/api/v1/snapshots/${SNAPSHOT}`),
      ).toBe(true),
    )
    expect(wrapper.find('#task-runs-title, .task-annotation-choice').exists()).toBe(false)
    resolveSnapshot()
    const heading = '.task-annotation-choice h2'
    await waitFor(() => expect(wrapper.find(heading).exists()).toBe(true))
    await waitFor(() => expect(document.activeElement).toBe(wrapper.get(heading).element))
    expect(wrapper.get('.task-context').classes()).toContain('app-resource-card')
    expect(wrapper.get('.task-annotation-choice').classes()).toContain('app-card')
    expect(wrapper.findAll('.app-card .app-card, .app-card .app-resource-card')).toHaveLength(0)
    // Once resolved, arriving run options must not steal focus from the current control.
    const change = wrapper.get<HTMLAnchorElement>('.task-context a')
    change.element.focus()
    await flushPromises()
    expect(document.activeElement).toBe(change.element)
  })

  it('offers manual entry before any classification without loading runs automatically', async () => {
    const { wrapper, server } = await mount(
      'annotation',
      taskServer({ runPages: [[]], resultPages: [[]] }),
    )
    await waitFor(() => expect(wrapper.findAll('.task-option')).toHaveLength(1))
    await wrapper.get('.task-option button').trigger('click')
    await waitFor(() => expect(wrapper.find('.task-annotation-choice').exists()).toBe(true))
    const entry = wrapper
      .findAll('.task-annotation-choice a')
      .find((a) => a.text() === messages.withoutEvidence)!
    await entry.trigger('click')
    await waitFor(() =>
      expect(wrapper.vm.$router.currentRoute.value.name).toBe('snapshotAnnotations'),
    )
    expect(
      server.requests.filter((r) => /\/runs(?:\/|$)|\/aggregations(?:\/|$)/.test(r.path)),
    ).toEqual([])
    expect(server.writes).toEqual([])
  })

  it('opens a chosen result in the full review workbench, not the plain register (D24)', async () => {
    const { wrapper } = await mount('annotation')
    await waitFor(() => expect(wrapper.findAll('.task-option')).toHaveLength(1))
    await wrapper.get('.task-option button').trigger('click')
    await waitFor(() => expect(wrapper.find('.task-annotation-choice').exists()).toBe(true))
    const chooseEvidence = wrapper
      .findAll('.task-annotation-choice a')
      .find((a) => a.text() === messages.chooseEvidence)!
    await chooseEvidence.trigger('click')
    await waitFor(() => expect(wrapper.find('#task-runs-title').exists()).toBe(true))
    const selectRun = wrapper.findAll('.task-option a').find((a) => a.text() === messages.select)!
    await selectRun.trigger('click')
    await waitFor(() => expect(wrapper.find('#task-results-title').exists()).toBe(true))
    const option = wrapper.get('.task-option a')
    expect(option.text()).toBe(messages.openReview)
    expect(option.attributes('href')).toBe(
      `/projects/${PROJECT}/runs/${RUN}/aggregations/${RESULT}/review`,
    )
    await option.trigger('click')
    await waitFor(() => expect(wrapper.vm.$router.currentRoute.value.name).toBe('review'))
  })

  it('distinguishes review result load failures from an empty collection', async () => {
    const { wrapper } = await mount(
      'review',
      taskServer({ failures: new Set([`/api/v1/projects/${PROJECT}/review-results`]) }),
    )
    await waitFor(() => expect(wrapper.get('.task-entry').text()).toContain(messages.resultError))
    expect(wrapper.get('.task-entry').text()).not.toContain(messages.noReviewSnapshots)
    const feedback = wrapper
      .findAll('.app-feedback')
      .find((entry) => entry.text().includes(messages.resultError))
    expect(feedback?.classes()).toContain('app-card')
    expect(button(wrapper, catalogues[locale].projects.retry).exists()).toBe(true)
  })

  it.each(['snapshot', 'run'] as const)(
    'rejects a mismatched %s selection before fetching results',
    async (mismatch) => {
      const server = taskServer(
        mismatch === 'snapshot'
          ? {
              snapshotOverrides: {
                [SNAPSHOT]: snapshot(SNAPSHOT, { project_id: 'other-project' }),
              },
            }
          : { runOverrides: { [RUN]: run(RUN, { dataset_snapshot_id: OTHER_SNAPSHOT }) } },
      )
      const { wrapper } = await mount(`review?snapshot=${SNAPSHOT}&run=${RUN}`, server)
      await waitFor(() =>
        expect(wrapper.get('.task-entry').text()).toContain(messages.selectionUnavailable),
      )
      expect(wrapper.find('.task-option').exists()).toBe(false)
      expect(wrapper.get('.app-feedback').classes()).toContain('app-card')
      expect(server.requests.some((r) => r.path.endsWith('/aggregations'))).toBe(false)
    },
  )
})
