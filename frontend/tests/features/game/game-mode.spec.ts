import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { createApiClient, type components } from '@/api'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { expectNoAxeViolations } from '../../helpers/axe'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'
import {
  AGG_ID,
  PROJECT_ID,
  RUN_ID,
  SNAPSHOT_ID,
  item,
  jsonResponse,
  newServer,
  reviewFetch,
  type Server as ReviewServer,
} from '../review/fixtures'

const USER_ID = 'a0000000-0000-0000-0000-000000000002'
const catalogues = { de, en } as const
const GAME_MODE_SOURCE = readFileSync(
  join(import.meta.dirname, '../../../src/features/game/GameModeView.vue'),
  'utf8',
)
const GAME_LEADERBOARD_SOURCE = readFileSync(
  join(import.meta.dirname, '../../../src/features/game/GameLeaderboard.vue'),
  'utf8',
)
const LAYOUT_SOURCE = readFileSync(
  join(import.meta.dirname, '../../../src/styles/layout.css'),
  'utf8',
)
const TOKENS_SOURCE = readFileSync(
  join(import.meta.dirname, '../../../src/styles/tokens.css'),
  'utf8',
)

function classRuleDeclarations(source: string, className: string): string[] {
  const styles = source.split('<style scoped>')[1]?.split('</style>')[0] ?? ''
  return [...styles.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selectors]) =>
      selectors
        ?.split(',')
        .map((selector) => selector.trim())
        .includes(`.${className}`),
    )
    .map(([, , declarations]) => declarations ?? '')
}

type GameRoundCreate = components['schemas']['GameRoundCreate']
type GameLeaderboard = components['schemas']['GameLeaderboard']

interface GameServer {
  review: ReviewServer
  roundPosts: GameRoundCreate[]
  failRoundAttempts: number
  leaderboard: GameLeaderboard
}

function gameServer(failRoundAttempts = 0): GameServer {
  const review = newServer({
    pages: [{ items: [item('demo-1')], next: null }],
    history: {
      snapshot_id: SNAPSHOT_ID,
      person_record_id: 'p-demo-1',
      tei_id: 'demo-1',
      revision: 0,
      workflow_state: 'unreviewed',
      current_annotation_id: null,
      annotations: [],
    },
  })
  return {
    review,
    roundPosts: [],
    failRoundAttempts,
    leaderboard: {
      project_id: PROJECT_ID,
      round_size: 10,
      total_players: 0,
      entries: [],
    },
  }
}

function gameClient(server: GameServer) {
  const fallback = reviewFetch(server.review)
  return createApiClient({
    fetch: async (request) => {
      const url = new URL(request.url)
      if (
        request.method === 'GET' &&
        url.pathname === `/api/v1/projects/${PROJECT_ID}/game-leaderboard`
      ) {
        return jsonResponse({
          ...server.leaderboard,
          round_size: Number(url.searchParams.get('round_size')),
        })
      }
      if (
        request.method === 'POST' &&
        url.pathname === `/api/v1/projects/${PROJECT_ID}/game-rounds`
      ) {
        const command = (await request.json()) as GameRoundCreate
        server.roundPosts.push(command)
        if (server.roundPosts.length <= server.failRoundAttempts) {
          return jsonResponse(
            {
              error: {
                code: 'internal_error',
                message: 'Round store unavailable',
                details: {},
                request_id: 'game-test',
              },
            },
            { status: 500 },
          )
        }
        const answered = command.annotation_ids.length
        const score = answered * 10
        const saved: components['schemas']['GameRound'] = {
          id: command.id,
          project_id: PROJECT_ID,
          aggregation_execution_id: command.aggregation_execution_id,
          reviewer_user_id: USER_ID,
          round_size: command.round_size,
          score,
          answered_count: answered,
          created_at: '2026-01-06T10:00:00Z',
        }
        server.leaderboard = {
          project_id: PROJECT_ID,
          round_size: command.round_size,
          total_players: 1,
          entries: [
            {
              rank: 1,
              round_id: command.id,
              reviewer_user_id: USER_ID,
              reviewer_display_name: 'Op',
              score,
              answered_count: answered,
              created_at: saved.created_at,
            },
          ],
        }
        return jsonResponse(saved, { status: 201 })
      }
      return fallback(request)
    },
  })
}

const mounted: VueWrapper[] = []
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  document.body.replaceChildren()
  window.localStorage.clear()
})

async function mountGame(locale: 'de' | 'en', server = gameServer()) {
  const wrapper = await mountApplicationAt(
    `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/game`,
    locale,
    gameClient(server),
  )
  mounted.push(wrapper)
  await waitFor(() => expect(wrapper.find('.game-setup').exists()).toBe(true))
  return { wrapper, server }
}

async function completeSingleAnswer(wrapper: VueWrapper): Promise<void> {
  await wrapper.get<HTMLInputElement>('.game-timer-option input').setValue(false)
  await wrapper.get<HTMLButtonElement>('.game-setup__start button').trigger('click')
  await waitFor(() => {
    const answer = wrapper.get<HTMLButtonElement>('.game-answer--female')
    expect(answer.attributes('disabled')).toBeUndefined()
  })
  expect(wrapper.find('.game-evidence').exists()).toBe(false)
  await wrapper.get<HTMLButtonElement>('.game-answer--female').trigger('click')
  await waitFor(() => expect(wrapper.find('.game-feedback').exists()).toBe(true))
  await wrapper.get<HTMLButtonElement>('.game-feedback__next button').trigger('click')
  await waitFor(() => expect(wrapper.find('.game-complete').exists()).toBe(true))
}

describe('game layout recipes', () => {
  it('uses the default 60rem page frame and the shared page heading anatomy', async () => {
    const { wrapper } = await mountGame('en')
    const page = wrapper.get('main.game-mode')

    expect(page.classes()).toContain('app-page-frame')
    expect(page.classes().filter((name) => name.startsWith('app-page-frame--'))).toEqual([])
    expect(wrapper.get('header.game-mode__header').classes()).toContain('app-page-heading')
    expect(wrapper.find('.game-mode__header > .app-page-heading__copy').exists()).toBe(true)
    expect(wrapper.get('h1').classes()).toContain('app-page-heading__title')
    expect(wrapper.get('.game-mode__header p').classes()).toContain('app-page-heading__description')

    const frameRule = /\.app-page-frame\s*\{([^}]*)\}/.exec(LAYOUT_SOURCE)?.[1] ?? ''
    expect(frameRule).toContain('max-inline-size: 60rem')
    expect(classRuleDeclarations(GAME_MODE_SOURCE, 'game-mode').join('\n')).not.toMatch(
      /max-(?:inline-)?(?:size|width)\s*:/,
    )
  })

  it('inherits the shared 16px card inset without nesting structural cards', async () => {
    const { wrapper } = await mountGame('en')

    expect(wrapper.get('.game-setup').classes()).toContain('app-card')
    expect(wrapper.get('.game-leaderboard').classes()).toContain('app-card')
    expect(wrapper.findAll('.app-card .app-card, .app-card .app-resource-card')).toHaveLength(0)

    const cardRule = /:is\(\.app-card, \.app-resource-card\)\s*\{([^}]*)\}/.exec(LAYOUT_SOURCE)?.[1]
    expect(cardRule).toContain('padding: var(--app-card-padding, var(--space-4))')
    expect(TOKENS_SOURCE).toMatch(/--space-4:\s*1rem;/)

    for (const className of ['game-setup', 'game-hud', 'game-complete']) {
      expect(classRuleDeclarations(GAME_MODE_SOURCE, className).join('\n')).not.toMatch(
        /(?:^|;)\s*padding(?:-[a-z-]+)?\s*:/,
      )
    }
    expect(
      classRuleDeclarations(GAME_LEADERBOARD_SOURCE, 'game-leaderboard').join('\n'),
    ).not.toMatch(/(?:^|;)\s*padding(?:-[a-z-]+)?\s*:/)
  })

  it('uses shared cards for every route-level feedback state', () => {
    expect(GAME_MODE_SOURCE.match(/class="game-mode__state app-card"/g)).toHaveLength(8)
    expect(GAME_MODE_SOURCE).not.toMatch(
      /<p\s+v-if="(?:session\.status|contextPending)[^"]*"[^>]*role="status"/,
    )
  })

  it('keeps playing and completion regions as sibling shared cards', async () => {
    const { wrapper } = await mountGame('en')

    await wrapper.get<HTMLInputElement>('.game-timer-option input').setValue(false)
    await wrapper.get<HTMLButtonElement>('.game-setup__start button').trigger('click')
    await waitFor(() =>
      expect(
        wrapper.get<HTMLButtonElement>('.game-answer--female').attributes('disabled'),
      ).toBeUndefined(),
    )

    expect(wrapper.get('.game-hud').classes()).toContain('app-card')
    expect(wrapper.get('.game-question').classes()).toEqual(
      expect.arrayContaining(['app-card', 'app-card--sectioned']),
    )
    expect(wrapper.findAll('.app-card .app-card, .app-card .app-resource-card')).toHaveLength(0)

    await wrapper.get<HTMLButtonElement>('.game-answer--female').trigger('click')
    await waitFor(() => expect(wrapper.find('.game-feedback').exists()).toBe(true))
    await wrapper.get<HTMLButtonElement>('.game-feedback__next button').trigger('click')
    await waitFor(() => expect(wrapper.find('.game-complete').exists()).toBe(true))

    expect(wrapper.get('.game-complete').classes()).toContain('app-card')
    expect(wrapper.get('.game-leaderboard').classes()).toContain('app-card')
    expect(wrapper.findAll('.app-card .app-card, .app-card .app-resource-card')).toHaveLength(0)
  })
})

describe.each(['de', 'en'] as const)('game mode in %s', (locale) => {
  it('saves ordinary annotations, reveals evidence, and persists the verified round', async () => {
    const { wrapper, server } = await mountGame(locale)
    await expectNoAxeViolations(wrapper.get('.game-mode').element)

    await wrapper.get<HTMLInputElement>('.game-timer-option input').setValue(false)
    await wrapper.get<HTMLButtonElement>('.game-setup__start button').trigger('click')
    await waitFor(() => {
      expect(
        wrapper.get<HTMLButtonElement>('.game-answer--female').attributes('disabled'),
      ).toBeUndefined()
    })
    expect(wrapper.find('.game-evidence').exists()).toBe(false)
    expect(wrapper.get('.game-decision').attributes('inert')).toBeUndefined()
    expect(wrapper.get('.game-decision').attributes('aria-hidden')).toBeUndefined()

    await wrapper.get<HTMLButtonElement>('.game-answer--female').trigger('click')
    await waitFor(() => expect(wrapper.find('.game-feedback').exists()).toBe(true))
    expect(document.activeElement).toBe(wrapper.get('#game-feedback-heading').element)
    expect(server.review.posts).toEqual([
      {
        snapshot_id: SNAPSHOT_ID,
        tei_id: 'demo-1',
        action: 'correct',
        aggregated_result_id: 'r-demo-1',
        expected_revision: 0,
        label: 'female',
      },
    ])
    expect(wrapper.get('.game-feedback').text()).toContain(
      catalogues[locale].game.feedback.saved.replace('{points}', '10'),
    )
    await waitFor(() => expect(wrapper.get('.game-evidence').text()).toContain('gnd'))

    // The saved revision must not replace the invisible four-choice layout with a conflict notice.
    expect(server.review.history.revision).toBe(1)
    const reservedDecision = wrapper.get('.game-decision')
    expect(reservedDecision.attributes('inert')).toBeDefined()
    expect(reservedDecision.attributes('aria-hidden')).toBe('true')
    expect(reservedDecision.findAll('.game-answer')).toHaveLength(4)
    for (const button of reservedDecision.findAll('.game-answer')) {
      expect(button.attributes('disabled')).toBeDefined()
    }
    expect(reservedDecision.text()).not.toContain(catalogues[locale].game.decision.changed)

    await wrapper.get<HTMLButtonElement>('.game-feedback__next button').trigger('click')
    await waitFor(() =>
      expect(document.activeElement).toBe(wrapper.get('#game-complete-heading').element),
    )
    await waitFor(() => expect(server.roundPosts).toHaveLength(1))
    await waitFor(() => expect(wrapper.find('.game-leaderboard__current').exists()).toBe(true))

    const round = server.roundPosts[0]!
    expect(round.aggregation_execution_id).toBe(AGG_ID)
    expect(round.round_size).toBe(10)
    expect(round.annotation_ids).toEqual(['new-1'])
    expect(wrapper.get('.game-complete').text()).toContain('10')
    expect(wrapper.get('.game-leaderboard__current').text()).toContain('Op')
    await expectNoAxeViolations(wrapper.get('.game-mode').element)
  })
})

describe('game clock', () => {
  it('advances only while playing, preserves answer time in feedback, and disposes its interval', async () => {
    let clockNow = Date.now()
    let clockTick: (() => void) | undefined
    let clockHandle: number | undefined
    let wrapper: VueWrapper | undefined
    const timers: Pick<Window, 'setInterval' | 'clearInterval'> = window
    const originalSetInterval = timers.setInterval.bind(window)
    const interval = vi
      .spyOn(timers, 'setInterval')
      .mockImplementation((handler, delay, ...args) => {
        if (delay === 250 && typeof handler === 'function') {
          clockTick = () => handler(...args)
          // Keep ordinary timers for query/mount work; drive only the game clock explicitly.
          clockHandle = originalSetInterval(() => undefined, delay)
          return clockHandle
        }
        return originalSetInterval(handler, delay, ...args)
      })
    const clearInterval = vi.spyOn(timers, 'clearInterval')
    const now = vi.spyOn(Date, 'now').mockImplementation(() => clockNow)

    try {
      const { wrapper: game } = await mountGame('en')
      wrapper = game
      expect(interval.mock.calls.filter(([, delay]) => delay === 250)).toHaveLength(1)
      if (clockTick === undefined || clockHandle === undefined) {
        throw new Error('The game clock interval was not registered')
      }

      clockNow += 10_000
      now.mockClear()
      clockTick()
      expect(now).not.toHaveBeenCalled()
      expect(game.find('.game-hud').exists()).toBe(false)

      await game.get<HTMLButtonElement>('.game-setup__start button').trigger('click')
      await waitFor(() =>
        expect(
          game.get<HTMLButtonElement>('.game-answer--female').attributes('disabled'),
        ).toBeUndefined(),
      )
      expect(game.get('.game-hud__stats > div:last-child dd').text()).toBe('0:00')

      clockNow += 65_000
      now.mockClear()
      clockTick()
      expect(now).toHaveBeenCalledOnce()
      await nextTick()
      expect(game.get('.game-hud__stats > div:last-child dd').text()).toBe('1:05')

      await game.get<HTMLButtonElement>('.game-answer--female').trigger('click')
      await waitFor(() => expect(game.find('.game-feedback').exists()).toBe(true))
      clockNow += 33_000
      now.mockClear()
      clockTick()
      expect(now).not.toHaveBeenCalled()
      await nextTick()
      expect(game.get('.game-hud__stats > div:last-child dd').text()).toBe('1:05')

      await game.get<HTMLButtonElement>('.game-feedback__next button').trigger('click')
      await waitFor(() => expect(game.find('.game-complete').exists()).toBe(true))
      expect(game.get('.game-complete__stats > div:nth-child(2) dd').text()).toBe('1:05')

      game.unmount()
      expect(clearInterval).toHaveBeenCalledWith(clockHandle)
    } finally {
      wrapper?.unmount()
      if (clockHandle !== undefined) window.clearInterval(clockHandle)
      now.mockRestore()
      clearInterval.mockRestore()
      interval.mockRestore()
    }
  })
})

describe('game project availability', () => {
  it('blocks a disabled project deep link before loading a review queue', async () => {
    const server = gameServer()
    server.review.gameEnabled = false
    const wrapper = await mountApplicationAt(
      `/projects/${PROJECT_ID}/runs/${RUN_ID}/aggregations/${AGG_ID}/game`,
      'en',
      gameClient(server),
    )
    mounted.push(wrapper)

    await waitFor(() => expect(wrapper.get('.game-mode').text()).toContain(en.game.disabled))
    expect(wrapper.find('.game-setup').exists()).toBe(false)
    const state = wrapper.get('.game-mode__state')
    expect(state.classes()).toEqual(expect.arrayContaining(['app-feedback', 'app-card']))
    expect(state.find('.app-card, .app-resource-card').exists()).toBe(false)
    expect(server.review.requests).toHaveLength(0)
  })
})

describe('game question pools', () => {
  it('defaults to open decisions and can play reviewed entries from the entire dataset', async () => {
    const server = gameServer()
    const reviewed = item('demo-1', {
      workflow_state: 'reviewed',
      review_revision: 2,
      current_annotation_id: 'prior',
    })
    server.review.pages = [
      {
        items: [reviewed, ...Array.from({ length: 4 }, (_, index) => item(`demo-${index + 2}`))],
        next: '1',
      },
      {
        items: Array.from({ length: 4 }, (_, index) => item(`demo-${index + 6}`)),
        next: null,
      },
    ]
    server.review.history = {
      snapshot_id: SNAPSHOT_ID,
      person_record_id: 'p-demo-1',
      tei_id: 'demo-1',
      revision: 2,
      workflow_state: 'reviewed',
      current_annotation_id: 'prior',
      annotations: [
        {
          id: 'prior',
          snapshot_id: SNAPSHOT_ID,
          person_record_id: 'p-demo-1',
          tei_id: 'demo-1',
          action: 'verify',
          label: 'male',
          reviewer_user_id: USER_ID,
          reviewer_display_name: 'Op',
          comment: null,
          aggregated_result_id: 'r-demo-1',
          supersedes_annotation_id: null,
          resulting_revision: 2,
          created_at: '2026-01-05T10:00:00Z',
        },
      ],
    }

    const { wrapper } = await mountGame('en', server)
    expect(server.review.requests.at(-1)?.getAll('workflow_states')).toEqual(['unreviewed'])

    await wrapper.get<HTMLInputElement>('#game-pool-all').setValue(true)
    await waitFor(() => {
      const query = server.review.requests.at(-1)
      expect(query?.getAll('workflow_states')).toEqual([])
      expect(query?.get('sort')).toBe('tei_id')
    })
    expect(wrapper.get('.game-setup').text()).toContain(en.game.pool.allHint)

    await wrapper.get<HTMLButtonElement>('.game-setup__start button').trigger('click')
    await waitFor(() => expect(server.review.requests.at(-1)?.get('cursor')).toBe('1'))
    await waitFor(() => {
      expect(wrapper.get('.game-hud').text()).toContain('9')
      expect(
        wrapper.get<HTMLButtonElement>('.game-answer--female').attributes('disabled'),
      ).toBeUndefined()
    })

    await wrapper.get<HTMLButtonElement>('.game-answer--female').trigger('click')
    await waitFor(() => expect(server.review.posts).toHaveLength(1))
    expect(server.review.posts[0]).toMatchObject({
      tei_id: 'demo-1',
      expected_revision: 2,
    })
  })

  it('continues a completed entire-dataset session on the next cursor page', async () => {
    const server = gameServer()
    server.review.recordCount = 12
    server.review.pages = [
      {
        items: Array.from({ length: 10 }, (_, index) => item(`demo-${index + 1}`)),
        next: '1',
      },
      {
        items: [item('demo-11'), item('demo-12')],
        next: null,
      },
    ]
    const { wrapper } = await mountGame('en', server)

    await wrapper.get<HTMLInputElement>('#game-pool-all').setValue(true)
    await waitFor(() => expect(server.review.requests.at(-1)?.get('sort')).toBe('tei_id'))
    await wrapper.get<HTMLButtonElement>('.game-setup__start button').trigger('click')

    for (let index = 1; index <= 10; index += 1) {
      await waitFor(() =>
        expect(wrapper.get('.game-question__header code').text()).toBe(`demo-${index}`),
      )
      await waitFor(() =>
        expect(wrapper.find('.game-decision__secondary button').exists()).toBe(true),
      )
      await wrapper.get<HTMLButtonElement>('.game-decision__secondary button').trigger('click')
    }

    await waitFor(() => expect(wrapper.find('.game-complete').exists()).toBe(true))
    await waitFor(() => expect(server.roundPosts).toHaveLength(1))
    await waitFor(() =>
      expect(
        wrapper.get<HTMLButtonElement>('.game-complete__actions button').attributes('disabled'),
      ).toBeUndefined(),
    )
    await wrapper.get<HTMLButtonElement>('.game-complete__actions button').trigger('click')
    await waitFor(() => expect(wrapper.find('.game-setup__start button').exists()).toBe(true))
    await wrapper.get<HTMLButtonElement>('.game-setup__start button').trigger('click')

    await waitFor(() => expect(wrapper.get('.game-question__header code').text()).toBe('demo-11'))
    expect(wrapper.get('.game-hud').text()).toContain('2')
    expect(server.review.requests.some((query) => query.get('cursor') === '1')).toBe(true)
  })
  it('fails closed when the next entire-dataset page cannot be loaded', async () => {
    const server = gameServer()
    server.review.recordCount = 9
    server.review.pages = [
      {
        items: Array.from({ length: 5 }, (_, index) => item(`demo-${index + 1}`)),
        next: '1',
      },
      {
        items: Array.from({ length: 4 }, (_, index) => item(`demo-${index + 6}`)),
        next: null,
      },
    ]
    server.review.failPageCursors = ['1']
    const { wrapper } = await mountGame('en', server)

    await wrapper.get<HTMLInputElement>('#game-pool-all').setValue(true)
    await waitFor(() => expect(server.review.requests.at(-1)?.get('sort')).toBe('tei_id'))
    await wrapper.get<HTMLButtonElement>('.game-setup__start button').trigger('click')

    await waitFor(() =>
      expect(wrapper.get('.game-setup').text()).toContain(en.game.queue.loadError),
    )
    expect(wrapper.find('.game-hud').exists()).toBe(false)
    expect(server.roundPosts).toHaveLength(0)
  })

  it('freezes round settings while additional pages load', async () => {
    const server = gameServer()
    server.review.recordCount = 5
    server.review.pages = [
      {
        items: [item('demo-1'), item('demo-2')],
        next: '1',
      },
      {
        items: [item('demo-3'), item('demo-4'), item('demo-5')],
        next: null,
      },
    ]
    let releasePage = (): void => {}
    server.review.pageGate = new Promise<void>((resolve) => {
      releasePage = resolve
    })
    const { wrapper } = await mountGame('en', server)

    const sizeOptions = wrapper.findAll<HTMLInputElement>('input[name="game-round-size"]')
    await sizeOptions[0]!.setValue()
    await wrapper.get<HTMLInputElement>('#game-pool-all').setValue(true)
    await waitFor(() => expect(server.review.requests.at(-1)?.get('sort')).toBe('tei_id'))
    await wrapper.get<HTMLButtonElement>('.game-setup__start button').trigger('click')
    await waitFor(() =>
      expect(server.review.requests.some((query) => query.get('cursor') === '1')).toBe(true),
    )

    expect(wrapper.get('#game-pool-open').attributes('disabled')).toBeDefined()
    expect(sizeOptions[1]!.attributes('disabled')).toBeDefined()
    expect(wrapper.get('.game-timer-option input').attributes('disabled')).toBeDefined()

    const standardSize = sizeOptions[1]!
    standardSize.element.checked = true
    standardSize.element.dispatchEvent(new Event('change', { bubbles: true }))
    await wrapper.vm.$nextTick()
    releasePage()

    for (let index = 1; index <= 5; index += 1) {
      await waitFor(() =>
        expect(wrapper.get('.game-question__header code').text()).toBe(`demo-${index}`),
      )
      await wrapper.get<HTMLButtonElement>('.game-decision__secondary button').trigger('click')
    }

    await waitFor(() => expect(server.roundPosts).toHaveLength(1))
    expect(server.roundPosts[0]?.round_size).toBe(10)
  })
})

describe('game annotation semantics', () => {
  it('records an answer matching the machine label as a verification', async () => {
    const server = gameServer()
    server.review.pages[0]!.items[0]!.machine_label = 'female'
    const { wrapper } = await mountGame('en', server)
    await wrapper.get<HTMLButtonElement>('.game-setup__start button').trigger('click')
    await waitFor(() => {
      expect(
        wrapper.get<HTMLButtonElement>('.game-answer--female').attributes('disabled'),
      ).toBeUndefined()
    })

    await wrapper.get<HTMLButtonElement>('.game-answer--female').trigger('click')
    await waitFor(() => expect(server.review.posts).toHaveLength(1))
    expect(server.review.posts[0]?.action).toBe('verify')
  })
})

describe('game round persistence recovery', () => {
  it('retries the same round id without duplicating its annotations', async () => {
    const { wrapper, server } = await mountGame('en', gameServer(1))
    await completeSingleAnswer(wrapper)
    await waitFor(() =>
      expect(wrapper.get('.game-complete').text()).toContain(en.game.complete.saveError),
    )
    expect(server.roundPosts).toHaveLength(1)
    const firstId = server.roundPosts[0]!.id

    const retry = wrapper
      .findAll<HTMLButtonElement>('.game-complete button')
      .find((button) => button.text() === en.game.complete.retrySave)
    if (!retry) throw new Error('Missing score retry action')
    await retry.trigger('click')
    await waitFor(() => expect(server.roundPosts).toHaveLength(2))
    await waitFor(() =>
      expect(wrapper.get('.game-complete').text()).toContain(en.game.complete.saved),
    )

    expect(server.roundPosts[1]!.id).toBe(firstId)
    expect(server.review.posts).toHaveLength(1)
  })
})
