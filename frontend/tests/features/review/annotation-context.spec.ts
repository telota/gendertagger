import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it } from 'vitest'

import { createAppI18n } from '@/app/i18n'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { privateQueryKey } from '@/composables/usePrivateQueryScope'
import ReviewDecision from '@/features/review/ReviewDecision.vue'
import { invalidateAfterDecision, postAnnotation } from '@/features/review/useAnnotate'
import type { AnnotationHistory, ReviewItem } from '@/features/review/useReviewData'

import { waitFor } from '../../helpers/wait'
import { HISTORY, item, newServer, reviewClient, SNAPSHOT_ID } from './fixtures'

afterEach(() => document.body.replaceChildren())

describe('snapshot-scoped annotation context', () => {
  it('keeps drafts during refresh but discards them when review permission is revoked', async () => {
    const client = new QueryClient()
    const wrapper = mount(ReviewDecision, {
      props: {
        item: item('demo-1') as ReviewItem,
        history: HISTORY as AnnotationHistory,
        historyRefreshing: false,
        canReview: true,
        contextReady: true,
      },
      global: {
        plugins: [createPinia(), createAppI18n('en'), [VueQueryPlugin, { queryClient: client }]],
        provide: { [API_CLIENT_KEY as symbol]: reviewClient(newServer()) },
      },
    })
    await wrapper.get('#decision-correct-female').setValue(true)
    await wrapper.get('#decision-comment').setValue('Only while authorized')
    await wrapper.setProps({ contextReady: false })
    expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element.value).toBe(
      'Only while authorized',
    )
    expect(wrapper.get<HTMLInputElement>('#decision-correct-female').element.checked).toBe(true)
    expect(wrapper.get<HTMLButtonElement>('#decision-save').element.disabled).toBe(true)
    await wrapper.setProps({ canReview: false })
    expect(wrapper.find('.decision-form').exists()).toBe(false)
    await wrapper.setProps({ canReview: true, contextReady: true })
    expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element.value).toBe('')
    expect(wrapper.get<HTMLInputElement>('#decision-correct-female').element.checked).toBe(false)
    expect(wrapper.get<HTMLButtonElement>('#decision-save').element.disabled).toBe(true)
    wrapper.unmount()
    client.clear()
  })

  it.each([undefined, null])(
    'can append a manual decision without result evidence (%s)',
    async (evidence) => {
      const server = newServer()
      await postAnnotation(reviewClient(server), {
        item: {
          snapshot_id: SNAPSHOT_ID,
          tei_id: 'demo-1',
          ...(evidence === undefined ? {} : { aggregated_result_id: evidence }),
        },
        action: 'correct',
        label: 'female',
        comment: '  Source attestation  ',
        expectedRevision: 0,
      })

      expect(server.posts).toEqual([
        {
          snapshot_id: SNAPSHOT_ID,
          tei_id: 'demo-1',
          action: 'correct',
          label: 'female',
          comment: 'Source attestation',
          expected_revision: 0,
        },
      ])
      expect(server.writes).toEqual(['POST /api/v1/annotations'])
    },
  )

  it('refreshes all same-snapshot projections, including empty queues, without changing other known snapshots', () => {
    const client = new QueryClient()
    const relatedKeys = [
      ['aggregations', 'current', 'review-items', 'low'],
      ['aggregations', 'current', 'review-summary'],
      ['aggregations', 'empty', 'review-items', 'contested'],
      ['aggregations', 'empty', 'review-summary'],
      ['aggregations', 'direct', 'review-item', 'demo-1'],
      ['aggregations', 'direct', 'review-summary'],
      ['snapshots', SNAPSHOT_ID, 'annotations', 'demo-1'],
    ].map((key) => privateQueryKey(key, 'reviewer'))
    for (const key of relatedKeys) client.setQueryData(key, {})
    client.setQueryData(relatedKeys[0]!, { pages: [{ items: [item('demo-1')] }] })
    client.setQueryData(relatedKeys[2]!, { pages: [{ items: [] }] })
    client.setQueryData(privateQueryKey(['aggregations', 'empty'], 'reviewer'), {
      run_id: 'other-run',
    })
    client.setQueryData(privateQueryKey(['runs', 'other-run'], 'reviewer'), {
      dataset_snapshot_id: SNAPSHOT_ID,
    })
    client.setQueryData(relatedKeys[4]!, item('demo-1'))

    const unrelatedKeys = [
      ['aggregations', 'unrelated', 'review-items', 'low'],
      ['aggregations', 'unrelated', 'review-summary'],
      ['snapshots', 'another-snapshot', 'annotations', 'demo-1'],
      ['snapshots', SNAPSHOT_ID, 'annotations', 'demo-2'],
      ['snapshots', SNAPSHOT_ID, 'people', 'demo-1'],
      ['aggregations', 'current', 'results', 'result-id', 'predictions'],
    ].map((key) => privateQueryKey(key, 'reviewer'))
    for (const key of unrelatedKeys) client.setQueryData(key, {})
    client.setQueryData(unrelatedKeys[0]!, {
      pages: [{ items: [item('demo-1', { snapshot_id: 'another-snapshot' })] }],
    })

    invalidateAfterDecision(client, { snapshotId: SNAPSHOT_ID, teiId: 'demo-1' }, 'reviewer')

    for (const key of relatedKeys) expect(client.getQueryState(key)?.isInvalidated).toBe(true)
    for (const key of unrelatedKeys) expect(client.getQueryState(key)?.isInvalidated).toBe(false)
    client.clear()
  })

  it('resolves cached snapshot ownership only from the current principal', () => {
    const client = new QueryClient()
    const summaryKey = privateQueryKey(['aggregations', 'shared', 'review-summary'], 'reviewer')
    const otherSummaryKey = privateQueryKey(['aggregations', 'shared', 'review-summary'], 'other')
    const directSummaryKey = privateQueryKey(
      ['aggregations', 'direct', 'review-summary'],
      'reviewer',
    )
    for (const key of [summaryKey, otherSummaryKey, directSummaryKey]) client.setQueryData(key, {})
    client.setQueryData(privateQueryKey(['aggregations', 'shared'], 'reviewer'), { run_id: 'run' })
    client.setQueryData(privateQueryKey(['runs', 'run'], 'reviewer'), {
      dataset_snapshot_id: SNAPSHOT_ID,
    })
    client.setQueryData(privateQueryKey(['aggregations', 'shared'], 'other'), { run_id: 'run' })
    client.setQueryData(privateQueryKey(['runs', 'run'], 'other'), {
      dataset_snapshot_id: 'another-snapshot',
    })
    client.setQueryData(
      privateQueryKey(['aggregations', 'direct', 'review-item', 'demo-1'], 'other'),
      item('demo-1', { snapshot_id: 'another-snapshot' }),
    )

    invalidateAfterDecision(client, { snapshotId: SNAPSHOT_ID }, 'reviewer')

    expect(client.getQueryState(summaryKey)?.isInvalidated).toBe(true)
    expect(client.getQueryState(directSummaryKey)?.isInvalidated).toBe(true)
    expect(client.getQueryState(otherSummaryKey)?.isInvalidated).toBe(false)
    client.clear()
  })

  it('refreshes cached empty queues and summaries when their ownership metadata is unavailable', () => {
    const client = new QueryClient()
    const listKey = privateQueryKey(['aggregations', 'unknown', 'review-items', 'low'], 'reviewer')
    const summaryKey = privateQueryKey(['aggregations', 'unknown', 'review-summary'], 'reviewer')
    client.setQueryData(listKey, { pages: [{ items: [] }] })
    client.setQueryData(summaryKey, { result_count: 0 })

    invalidateAfterDecision(client, { snapshotId: SNAPSHOT_ID }, 'reviewer')

    expect(client.getQueryState(listKey)?.isInvalidated).toBe(true)
    expect(client.getQueryState(summaryKey)?.isInvalidated).toBe(true)
    client.clear()
  })

  it.each(['snapshot', 'evidence'] as const)(
    'clears the draft for a changed %s even when the TEI ID is unchanged',
    async (context) => {
      const client = new QueryClient()
      const wrapper = mount(ReviewDecision, {
        props: {
          item: item('demo-1') as ReviewItem,
          history: HISTORY as AnnotationHistory,
          historyRefreshing: false,
          canReview: true,
        },
        global: {
          plugins: [createPinia(), createAppI18n('en'), [VueQueryPlugin, { queryClient: client }]],
          provide: { [API_CLIENT_KEY as symbol]: reviewClient(newServer()) },
        },
      })
      await wrapper.get('#decision-correct-female').setValue(true)
      await wrapper.get('#decision-comment').setValue('Only for the original context')
      await wrapper.setProps({
        item: item(
          'demo-1',
          context === 'snapshot'
            ? { snapshot_id: 'another-snapshot' }
            : { aggregated_result_id: 'another-result' },
        ) as ReviewItem,
      })

      expect(wrapper.get<HTMLInputElement>('#decision-correct-female').element.checked).toBe(false)
      expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element.value).toBe('')
      expect(wrapper.get('#decision-save').attributes('disabled')).toBeDefined()
      if (context === 'snapshot') {
        await wrapper.get('#decision-correct-female').setValue(true)
        expect(wrapper.get('#decision-save').attributes('disabled')).toBeDefined()
        await wrapper.setProps({
          history: { ...HISTORY, snapshot_id: 'another-snapshot' } as AnnotationHistory,
        })
        expect(wrapper.get('#decision-save').attributes('disabled')).toBeUndefined()
      }
      wrapper.unmount()
      client.clear()
    },
  )

  it.each(['ok', 'conflict'] as const)(
    'does not apply a late %s response to the same TEI ID in another snapshot',
    async (postOutcome) => {
      let finish!: () => void
      const gate = new Promise<void>((resolve) => {
        finish = resolve
      })
      const server = newServer({ gate, postOutcome })
      const client = new QueryClient()
      const wrapper = mount(ReviewDecision, {
        attachTo: document.body,
        props: {
          item: item('demo-1') as ReviewItem,
          history: HISTORY as AnnotationHistory,
          historyRefreshing: false,
          canReview: true,
        },
        global: {
          plugins: [createPinia(), createAppI18n('en'), [VueQueryPlugin, { queryClient: client }]],
          provide: { [API_CLIENT_KEY as symbol]: reviewClient(server) },
        },
      })
      await wrapper.get('#decision-correct-female').setValue(true)
      await wrapper.get('.decision-form').trigger('submit')
      await waitFor(() => expect(server.posts).toHaveLength(1))
      await wrapper.setProps({
        item: item('demo-1', { snapshot_id: 'another-snapshot' }) as ReviewItem,
      })
      await wrapper.get('#decision-correct-unknown').setValue(true)
      await wrapper.get('#decision-comment').setValue('A different snapshot')
      wrapper.get<HTMLTextAreaElement>('#decision-comment').element.focus()
      finish()
      await waitFor(() => expect(server.history.revision).toBe(3))
      await flushPromises()

      expect(wrapper.get('.decision-saved').text()).toBe('')
      expect(wrapper.find('.decision-conflict').exists()).toBe(false)
      expect(wrapper.get<HTMLInputElement>('#decision-correct-unknown').element.checked).toBe(true)
      expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element.value).toBe(
        'A different snapshot',
      )
      expect(document.activeElement).toBe(wrapper.get('#decision-comment').element)
      expect(server.posts[0]).toMatchObject({ snapshot_id: SNAPSHOT_ID, expected_revision: 2 })
      wrapper.unmount()
      client.clear()
    },
  )
})
