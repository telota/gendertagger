import { flushPromises, type VueWrapper } from '@vue/test-utils'
// See import.spec.ts: a jsdom `File` inside a `FormData` crashes Vitest's fetch-compat layer.
import { File as NodeFile } from 'node:buffer'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { mountApplicationAt } from '../../helpers/render'

const MIB = 1024 * 1024

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function testFile(content: string, name: string): File {
  return new NodeFile([content], name, { type: 'application/octet-stream' }) as unknown as File
}

function selectFiles(wrapper: VueWrapper, files: File[]): void {
  const input = wrapper.get('#import-file').element as HTMLInputElement
  Object.defineProperty(input, 'files', { value: files, configurable: true })
  input.dispatchEvent(new Event('change'))
}

async function choose(wrapper: VueWrapper, switcher: string, label: string): Promise<void> {
  const listbox = wrapper.get(switcher)
  await listbox.get('button').trigger('click')
  await listbox
    .findAll('li')
    .find((item) => item.text() === label)
    ?.trigger('click')
}

const catalogues = { de, en } as const
const OPERATOR = { id: 'a0000000-0000-0000-0000-000000000002', display_name: 'Op', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'
const SNAPSHOT = {
  id: SNAPSHOT_ID,
  project_id: PROJECT_ID,
  source_artifact_id: 'd0000000-0000-0000-0000-000000000001',
  source_sha256: 'a'.repeat(64),
  parser_version: '1',
  status: 'pending',
  created_at: '2026-01-01T00:00:00Z',
}

interface Setup {
  limits?: { part: number; total: number } | 'unavailable'
}

function importClient(setup: Setup, sent: FormData[]) {
  const { limits = { part: 10 * MIB, total: 20 * MIB } } = setup
  return createApiClient({
    fetch: async (request) => {
      const { pathname } = new URL(request.url)
      if (pathname === '/api/v1/branding') return jsonResponse({})
      if (pathname === '/api/v1/me') return jsonResponse(OPERATOR)
      if (pathname === '/api/v1/auth/session') {
        return jsonResponse({ must_change_password: false, keep_signed_in: false })
      }
      if (pathname === `/api/v1/projects/${PROJECT_ID}`) {
        return jsonResponse({
          id: PROJECT_ID,
          slug: 'p',
          display_name: 'Project A',
          description: null,
          current_user_role: 'operator',
          created_at: '2026-01-01T00:00:00Z',
        })
      }
      if (pathname === '/api/v1/snapshot-upload-limits') {
        if (limits === 'unavailable') return jsonResponse({}, { status: 500 })
        return jsonResponse({
          max_upload_part_bytes: limits.part,
          max_total_upload_bytes: limits.total,
          import_limits: { max_member_count: 128, max_total_expanded_bytes: 500 * MIB },
        })
      }
      if (pathname === `/api/v1/projects/${PROJECT_ID}/snapshots`) {
        sent.push(await request.formData())
        return jsonResponse(SNAPSHOT, { status: 202 })
      }
      if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}`) return jsonResponse(SNAPSHOT)
      return jsonResponse({}, { status: 404 })
    },
  })
}

afterEach(() => {
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('import formats and limits in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].projects.import
  const path = `/projects/${PROJECT_ID}/import`

  async function mountImport(setup: Setup = {}) {
    const sent: FormData[] = []
    const wrapper = await mountApplicationAt(path, locale, importClient(setup, sent))
    await flushPromises()
    return { wrapper, sent }
  }

  it('shows the upload limits before anything is chosen', async () => {
    const { wrapper } = await mountImport()

    const text = wrapper.get('.import-limits').text()
    expect(text).toMatch(/10[.,]0/)
    expect(text).toMatch(/20[.,]0/)
    expect(wrapper.find('.import-limits-archive').exists()).toBe(false)
    expect(wrapper.get('#import-file').attributes('aria-describedby')).toBe('import-limits')
  })

  it('adds the archive bounds once an archive packaging is chosen', async () => {
    const { wrapper } = await mountImport()

    await choose(wrapper, '.import-packaging', messages.packaging.zip)

    expect(wrapper.get('.import-limits-archive').text()).toMatch(/128/)
  })

  it('says so, without blocking, when the limits cannot be loaded', async () => {
    const { wrapper } = await mountImport({ limits: 'unavailable' })

    expect(wrapper.get('.import-limits').text()).toContain(messages.limits.unavailable)
    selectFiles(wrapper, [testFile('x', 'a.xml')])
    await flushPromises()
    expect(wrapper.get('.import-submit').attributes('disabled')).toBeUndefined()
  })

  it('offers a delivery choice only for TEI', async () => {
    const { wrapper } = await mountImport()
    expect(wrapper.find('.import-packaging').exists()).toBe(true)

    await choose(wrapper, '.import-format', 'CSV')

    expect(wrapper.find('.import-packaging').exists()).toBe(false)
  })

  it('uploads a ZIP archive with its packaging', async () => {
    const { wrapper, sent } = await mountImport()

    await choose(wrapper, '.import-packaging', messages.packaging.zip)
    selectFiles(wrapper, [testFile('zip', 'collection.zip')])
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(sent[0]?.get('packaging')).toBe('zip')
    expect(sent[0]?.get('source_format')).toBe('tei')
    expect(sent[0]?.getAll('source')).toHaveLength(1)
  })

  it('uploads several loose TEI files as repeated source parts', async () => {
    const { wrapper, sent } = await mountImport()

    await choose(wrapper, '.import-packaging', messages.packaging.loose)
    expect(wrapper.get('#import-file').attributes('multiple')).toBeDefined()
    selectFiles(wrapper, [testFile('<a/>', 'a.xml'), testFile('<b/>', 'b.xml')])
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(sent[0]?.get('packaging')).toBe('loose')
    expect(sent[0]?.getAll('source')).toHaveLength(2)
  })

  it('falls back to a single file when the format leaves TEI', async () => {
    const { wrapper, sent } = await mountImport()

    await choose(wrapper, '.import-packaging', messages.packaging.zip)
    await choose(wrapper, '.import-format', 'CSV')
    selectFiles(wrapper, [testFile('a,b', 'people.csv')])
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(sent[0]?.get('packaging')).toBe('single')
    expect(sent[0]?.get('source_format')).toBe('csv')
  })

  it('drops a selection made for another packaging', async () => {
    const { wrapper } = await mountImport()
    selectFiles(wrapper, [testFile('x', 'a.xml')])
    await flushPromises()
    expect(wrapper.get('.import-submit').attributes('disabled')).toBeUndefined()

    await choose(wrapper, '.import-packaging', messages.packaging.loose)
    await flushPromises()

    expect(wrapper.get('.import-submit').attributes('disabled')).toBeDefined()
  })

  it('refuses a ZIP chosen as a single TEI file, naming the fix, before uploading', async () => {
    const { wrapper, sent } = await mountImport()

    selectFiles(wrapper, [testFile('zip', 'collection.zip')])
    await flushPromises()

    expect(wrapper.get('.import-error').text()).toBe(messages.errors.looksLikeArchive)
    expect(wrapper.get('.import-submit').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(sent).toHaveLength(0)
  })

  it('refuses a plain XML file chosen under an archive delivery', async () => {
    const { wrapper } = await mountImport()

    await choose(wrapper, '.import-packaging', messages.packaging.zip)
    selectFiles(wrapper, [testFile('<a/>', 'a.xml')])
    await flushPromises()

    expect(wrapper.get('.import-error').text()).toBe(messages.errors.notAnArchive)
    expect(wrapper.get('.import-submit').attributes('disabled')).toBeDefined()
  })

  it('accepts a tar.gz under the tar.gz delivery', async () => {
    const { wrapper } = await mountImport()

    await choose(wrapper, '.import-packaging', messages.packaging.tarGz)
    selectFiles(wrapper, [testFile('x', 'collection.tar.gz')])
    await flushPromises()

    expect(wrapper.find('.import-error').exists()).toBe(false)
    expect(wrapper.get('.import-submit').attributes('disabled')).toBeUndefined()
  })

  it('refuses a file over the per-file bound before uploading', async () => {
    const { wrapper, sent } = await mountImport({ limits: { part: 4, total: 100 } })

    selectFiles(wrapper, [testFile('longer than four bytes', 'big.xml')])
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(messages.errors.partTooLarge)
    expect(wrapper.get('.import-submit').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(sent).toHaveLength(0)
  })

  it('refuses files that together exceed the total bound', async () => {
    const { wrapper } = await mountImport({ limits: { part: 100, total: 6 } })

    await choose(wrapper, '.import-packaging', messages.packaging.loose)
    selectFiles(wrapper, [testFile('1234', 'a.xml'), testFile('5678', 'b.xml')])
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(messages.errors.totalTooLarge)
  })
})
