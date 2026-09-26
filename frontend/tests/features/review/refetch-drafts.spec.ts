import { useQueryClient } from '@tanstack/vue-query'
import { type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import en from '@/locales/en.json'
import { mountApplicationAt } from '../../helpers/render'
import { PROJECT, SNAPSHOT, taskClient, taskServer } from '../../helpers/taskFixtures'
import { waitFor } from '../../helpers/wait'
import { AGG_ID, RUN_ID, newServer, reviewClient } from './fixtures'

const mounted: VueWrapper[] = []
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount()
  document.body.replaceChildren()
})

const scenarios = [
  {
    mode: 'raw',
    resource: 'person',
    path: `/api/v1/snapshots/${SNAPSHOT}/annotation-items/demo-1`,
    key: ['snapshot-annotation-item', SNAPSHOT],
  },
  {
    mode: 'raw',
    resource: 'snapshot',
    path: `/api/v1/snapshots/${SNAPSHOT}`,
    key: ['imported-snapshot'],
  },
  {
    mode: 'raw',
    resource: 'project',
    path: `/api/v1/projects/${PROJECT}`,
    key: ['projects', PROJECT],
  },
  {
    mode: 'raw',
    resource: 'history',
    path: '/api/v1/annotations',
    key: ['snapshots', SNAPSHOT, 'annotations'],
  },
  {
    mode: 'evidence',
    resource: 'aggregation',
    path: `/api/v1/aggregations/${AGG_ID}`,
    key: ['aggregations', AGG_ID],
  },
  { mode: 'evidence', resource: 'run', path: `/api/v1/runs/${RUN_ID}`, key: ['runs', RUN_ID] },
  {
    mode: 'evidence',
    resource: 'project',
    path: `/api/v1/projects/${PROJECT}`,
    key: ['projects', PROJECT],
  },
  {
    mode: 'evidence',
    resource: 'snapshot',
    path: `/api/v1/snapshots/${SNAPSHOT}`,
    key: ['imported-snapshot'],
  },
  {
    mode: 'evidence',
    resource: 'history',
    path: '/api/v1/annotations',
    key: ['snapshots', SNAPSHOT, 'annotations'],
  },
] as const

describe('authorized review drafts during refetch', () => {
  it.each(scenarios)(
    'retains $mode $resource drafts after 500, blocks save, then recovers',
    async ({ mode, resource, path, key }) => {
      let status = 200
      const client = mode === 'raw' ? taskClient(taskServer()) : reviewClient(newServer())
      client.use({
        onResponse({ request, response }) {
          return new URL(request.url).pathname === path && status !== 200
            ? new Response(
                JSON.stringify({ error: { code: 'internal_error', message: 'Unavailable' } }),
                { status, headers: { 'content-type': 'application/json' } },
              )
            : response
        },
      })
      const route =
        mode === 'raw'
          ? `/projects/${PROJECT}/snapshots/${SNAPSHOT}/annotations/demo-1`
          : `/projects/${PROJECT}/runs/${RUN_ID}/aggregations/${AGG_ID}/review`
      const wrapper = await mountApplicationAt(route, 'en', client)
      mounted.push(wrapper)
      await waitFor(() => expect(wrapper.find('#decision-comment').exists()).toBe(true))
      await wrapper.get('#decision-correct-female').setValue(true)
      await wrapper.get('#decision-comment').setValue('Keep the editorial draft')
      await waitFor(() =>
        expect(wrapper.get<HTMLButtonElement>('#decision-save').element.disabled).toBe(false),
      )
      const field = wrapper.get<HTMLTextAreaElement>('#decision-comment').element
      const cache = wrapper.vm.$.appContext.app.runWithContext(() => useQueryClient())

      status = 500
      await cache.refetchQueries({ queryKey: key })
      await waitFor(() =>
        expect(wrapper.get<HTMLButtonElement>('#decision-save').element.disabled).toBe(true),
      )
      expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element).toBe(field)
      expect(field.value).toBe('Keep the editorial draft')
      expect(wrapper.text()).toContain(
        resource === 'history' ? en.review.detail.history.loadError : en.review.refreshError,
      )

      status = 200
      await cache.refetchQueries({ queryKey: key })
      await waitFor(() =>
        expect(wrapper.get<HTMLButtonElement>('#decision-save').element.disabled).toBe(false),
      )
      expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element).toBe(field)
      expect(field.value).toBe('Keep the editorial draft')

      if (resource !== 'history') {
        status = 403
        await cache.refetchQueries({ queryKey: key })
        await waitFor(() => expect(wrapper.find('#decision-comment').exists()).toBe(false))
        status = 200
        await cache.refetchQueries({ queryKey: key })
        await waitFor(() => expect(wrapper.find('#decision-comment').exists()).toBe(true))
        expect(wrapper.get<HTMLTextAreaElement>('#decision-comment').element.value).toBe('')
      }
    },
  )
})
