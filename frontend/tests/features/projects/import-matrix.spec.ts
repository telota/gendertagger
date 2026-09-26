import { flushPromises, type VueWrapper } from '@vue/test-utils'
// See import.spec.ts: a jsdom `File` inside a `FormData` crashes Vitest's fetch-compat layer.
import { File as NodeFile } from 'node:buffer'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { expectNoAxeViolations } from '../../helpers/axe'
import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

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

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

function selectFiles(wrapper: VueWrapper, files: File[]): void {
  const input = wrapper.get('.import-file-input').element as HTMLInputElement
  Object.defineProperty(input, 'files', { value: files, configurable: true })
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

function dispatchDrag(wrapper: VueWrapper, type: string, files: File[] = []): Event {
  const event = new Event(type, { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'dataTransfer', {
    value: { files, types: ['Files'] },
  })
  wrapper.get('.import-dropzone').element.dispatchEvent(event)
  return event
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
  limits?: { part: number; total: number; members?: number } | 'unavailable'
  snapshotResponse?: Promise<Response>
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
          import_limits: {
            max_member_count: limits.members ?? 128,
            max_total_expanded_bytes: 500 * MIB,
          },
        })
      }
      if (pathname === `/api/v1/projects/${PROJECT_ID}/snapshots`) {
        sent.push(await request.formData())
        return setup.snapshotResponse ?? jsonResponse(SNAPSHOT, { status: 202 })
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

  it('offers an accessible multi-file picker and dropzone before anything is chosen', async () => {
    const { wrapper } = await mountImport()

    const input = wrapper.get<HTMLInputElement>('.import-file-input')
    const accepted = (input.attributes('accept') ?? '').toLowerCase()
    for (const extension of ['.xml', '.tei', '.zip', '.tar.gz', '.tgz', '.csv', '.xlsx', '.json']) {
      expect(accepted).toContain(extension)
    }
    expect(accepted).not.toContain('/')
    expect(input.attributes('multiple')).toBeDefined()
    expect(input.attributes('tabindex')).toBe('-1')
    expect(wrapper.get('.import-dropzone').isVisible()).toBe(true)
    expect(wrapper.get('.import-browse').isVisible()).toBe(true)
    expect(wrapper.find('.import-detected-source').exists()).toBe(false)
    const queueAnnouncement = wrapper.get('.import-queue-announcement')
    expect(queueAnnouncement.text()).toBe('')
    expect(queueAnnouncement.attributes()).toMatchObject({
      role: 'status',
      'aria-live': 'polite',
      'aria-atomic': 'true',
    })
    const text = wrapper.get('.import-limits').text()
    expect(text).toMatch(/10[.,]0/)
    expect(text).toMatch(/20[.,]0/)
    expect(wrapper.find('.import-limits-archive').exists()).toBe(false)
    expect(input.attributes('aria-describedby')?.split(/\s+/)).toContain(
      wrapper.get('.import-limits').attributes('id'),
    )
    await expectNoAxeViolations(wrapper.get('main').element)
  })

  it('adds the archive bounds once an archive is selected', async () => {
    const { wrapper } = await mountImport()

    selectFiles(wrapper, [testFile('zip', 'collection.zip')])
    await flushPromises()

    expect(wrapper.get('.import-limits-archive').text()).toMatch(/128/)
  })

  it('says so, without blocking, when the limits cannot be loaded', async () => {
    const { wrapper } = await mountImport({ limits: 'unavailable' })

    expect(wrapper.get('.import-limits').text()).toContain(messages.limits.unavailable)
    selectFiles(wrapper, [testFile('x', 'a.xml')])
    await flushPromises()
    expect(wrapper.get('.import-submit').attributes('disabled')).toBeUndefined()
  })

  const inferenceCases: {
    name: string
    files: () => File[]
    formatLabel: string
    packagingLabel: string
    sourceFormat: string
    packaging: string
  }[] = [
    {
      name: 'one XML file',
      files: () => [testFile('<a/>', 'register.xml')],
      formatLabel: 'TEI XML',
      packagingLabel: messages.packaging.single,
      sourceFormat: 'tei',
      packaging: 'single',
    },
    {
      name: 'one case-insensitive TEI file',
      files: () => [testFile('<a/>', 'register.TEI')],
      formatLabel: 'TEI XML',
      packagingLabel: messages.packaging.single,
      sourceFormat: 'tei',
      packaging: 'single',
    },
    {
      name: 'several XML files',
      files: () => [testFile('<a/>', 'a.xml'), testFile('<b/>', 'b.xml')],
      formatLabel: 'TEI XML',
      packagingLabel: messages.packaging.loose,
      sourceFormat: 'tei',
      packaging: 'loose',
    },
    {
      name: 'a ZIP archive',
      files: () => [testFile('zip', 'collection.zip')],
      formatLabel: 'TEI XML',
      packagingLabel: messages.packaging.zip,
      sourceFormat: 'tei',
      packaging: 'zip',
    },
    {
      name: 'a TAR.GZ archive',
      files: () => [testFile('tar', 'collection.tar.gz')],
      formatLabel: 'TEI XML',
      packagingLabel: messages.packaging.tarGz,
      sourceFormat: 'tei',
      packaging: 'tar_gz',
    },
    {
      name: 'a case-insensitive TGZ archive',
      files: () => [testFile('tar', 'collection.TGZ')],
      formatLabel: 'TEI XML',
      packagingLabel: messages.packaging.tarGz,
      sourceFormat: 'tei',
      packaging: 'tar_gz',
    },
    {
      name: 'a CSV register',
      files: () => [
        testFile('xml:id,persName,birth,death,event,note,idno\nS1,[],,,[],,[]\n', 'people.csv'),
      ],
      formatLabel: 'CSV',
      packagingLabel: messages.packaging.single,
      sourceFormat: 'csv',
      packaging: 'single',
    },
    {
      name: 'an XLSX register',
      files: () => [testFile('sheet', 'people.xlsx')],
      formatLabel: 'XLSX',
      packagingLabel: messages.packaging.single,
      sourceFormat: 'xlsx',
      packaging: 'single',
    },
    {
      name: 'a JSON register',
      files: () => [testFile('{}', 'people.json')],
      formatLabel: 'JSON',
      packagingLabel: messages.packaging.single,
      sourceFormat: 'json',
      packaging: 'single',
    },
  ]

  for (const testCase of inferenceCases) {
    it(`infers ${testCase.name} and sends the explicit API fields`, async () => {
      const { wrapper, sent } = await mountImport()
      const files = testCase.files()

      selectFiles(wrapper, files)
      await waitFor(() =>
        expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(false),
      )
      const detected = wrapper.get('.import-detected-source').text()
      expect(detected).toContain(testCase.formatLabel)
      expect(detected).toContain(testCase.packagingLabel)
      expect(wrapper.findAll('.import-file-item')).toHaveLength(files.length)
      expect(wrapper.find('.import-selection-error').exists()).toBe(false)

      await wrapper.get('form').trigger('submit')
      await flushPromises()
      expect(sent).toHaveLength(1)
      expect(sent[0]?.get('source_format')).toBe(testCase.sourceFormat)
      expect(sent[0]?.get('packaging')).toBe(testCase.packaging)
      expect(sent[0]?.getAll('source')).toHaveLength(files.length)
    })
  }

  it('supports drag feedback and feeds dropped files through the same inference path', async () => {
    const { wrapper } = await mountImport()
    const dropzone = wrapper.get('.import-dropzone')
    const file = testFile('{}', 'people.json')

    const enter = dispatchDrag(wrapper, 'dragenter', [file])
    await flushPromises()
    expect(enter.defaultPrevented).toBe(true)
    expect(dropzone.classes()).toContain('import-dropzone--active')
    const over = dispatchDrag(wrapper, 'dragover', [file])
    expect(over.defaultPrevented).toBe(true)
    dispatchDrag(wrapper, 'dragleave', [file])
    await flushPromises()
    expect(dropzone.classes()).not.toContain('import-dropzone--active')

    dispatchDrag(wrapper, 'dragenter', [file])
    const dropped = dispatchDrag(wrapper, 'drop', [file])
    await flushPromises()
    expect(dropped.defaultPrevented).toBe(true)
    expect(dropzone.classes()).not.toContain('import-dropzone--active')
    expect(wrapper.get('.import-file-item').text()).toContain('people.json')
    expect(wrapper.get('.import-detected-source').text()).toContain('JSON')
    expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(false)
  })

  it('adds compatible XML files and leaves the current selection unchanged after a rejected addition', async () => {
    const { wrapper } = await mountImport()
    const queueAnnouncement = wrapper.get('.import-queue-announcement')
    expect(queueAnnouncement.text()).toBe('')
    selectFiles(wrapper, [testFile('<a/>', 'a.xml')])
    await flushPromises()

    dispatchDrag(wrapper, 'drop', [testFile('<b/>', 'b.xml')])
    await flushPromises()
    expect(wrapper.findAll('.import-file-item')).toHaveLength(2)
    expect(wrapper.get('.import-file-selection').attributes('aria-live')).toBeUndefined()
    expect(wrapper.get('.import-file-total').attributes('role')).toBeUndefined()
    expect(wrapper.get('.import-queue-announcement').element).toBe(queueAnnouncement.element)
    expect(wrapper.get('.import-queue-announcement').text()).toContain('2')
    expect(wrapper.get('.import-queue-announcement').text()).toContain('TEI XML')
    expect(wrapper.get('.import-detected-source').attributes('role')).toBeUndefined()
    expect(wrapper.get('.import-detected-source').text()).toContain(messages.packaging.loose)

    dispatchDrag(wrapper, 'drop', [testFile('a,b', 'people.csv')])
    await flushPromises()
    expect(wrapper.findAll('.import-file-item').map((item) => item.text())).toEqual([
      expect.stringContaining('a.xml'),
      expect.stringContaining('b.xml'),
    ])
    expect(wrapper.get('.import-selection-error').text()).toBe(messages.errors.unsupportedSelection)
    expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(false)
  })

  it('removes files, recomputes delivery, and clears the native selection', async () => {
    const { wrapper } = await mountImport()
    selectFiles(wrapper, [testFile('<a/>', 'a.xml'), testFile('<b/>', 'b.xml')])
    await flushPromises()
    expect(wrapper.get('.import-detected-source').text()).toContain(messages.packaging.loose)
    const originalInput = wrapper.get<HTMLInputElement>('.import-file-input').element
    const second = wrapper
      .findAll('.import-file-item')
      .find((item) => item.text().includes('b.xml'))
    expect(second).toBeDefined()
    const remove = second!.get('.import-file-remove')
    expect(remove.attributes('aria-label')).toContain('b.xml')
    await remove.trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.import-file-item')).toHaveLength(1)
    expect(wrapper.get('.import-file-item').text()).toContain('a.xml')
    expect(wrapper.get('.import-detected-source').text()).toContain(messages.packaging.single)
    expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(false)

    await wrapper.get('.import-files-clear').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.import-file-item')).toHaveLength(0)
    expect(wrapper.find('.import-detected-source').exists()).toBe(false)
    expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(true)
    const resetInput = wrapper.get<HTMLInputElement>('.import-file-input').element
    expect(resetInput).not.toBe(originalInput)
    expect(resetInput.files?.length ?? 0).toBe(0)
  })

  it('rejects unsupported, mixed, multiple TEI, and multiple tabular selections', async () => {
    const { wrapper, sent } = await mountImport()
    const invalidSelections = [
      [testFile('plain', 'people.txt')],
      [testFile('<a/>', 'a.xml'), testFile('a,b', 'b.csv')],
      [testFile('<a/>', 'a.tei'), testFile('<b/>', 'b.tei')],
      [testFile('a,b', 'a.csv'), testFile('c,d', 'b.csv')],
    ]

    for (const files of invalidSelections) {
      selectFiles(wrapper, files)
      await flushPromises()
      expect(wrapper.get('.import-selection-error').attributes('role')).toBe('alert')
      expect(wrapper.find('.import-detected-source').exists()).toBe(false)
      expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(true)
      await wrapper.get('form').trigger('submit')
      expect(sent).toHaveLength(0)
    }

    selectFiles(wrapper, [testFile('{}', 'people.json')])
    await flushPromises()
    expect(wrapper.find('.import-selection-error').exists()).toBe(false)
    expect(wrapper.get('.import-detected-source').text()).toContain('JSON')
    expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(false)
  })

  it('shows the applicable tabular and JSON profile requirements', async () => {
    const { wrapper } = await mountImport()
    expect(wrapper.find('.import-profile').exists()).toBe(false)

    selectFiles(wrapper, [testFile('xml:id,persName,birth,death,event,note,idno\n', 'people.csv')])
    await flushPromises()

    const hint = wrapper.get('.import-profile')
    expect(hint.text()).toContain(messages.profile.tabularIntro)
    expect(hint.findAll('code').map((code) => code.text())).toEqual([
      'xml:id',
      'persName',
      'birth',
      'death',
      'event',
      'note',
      'idno',
    ])
    const describedBy = wrapper
      .get('.import-file-input')
      .attributes('aria-describedby')
      ?.split(/\s+/)
    expect(describedBy).toContain(wrapper.get('.import-limits').attributes('id'))
    expect(describedBy).toContain(hint.attributes('id'))

    await wrapper.get('.import-files-clear').trigger('click')
    await flushPromises()
    selectFiles(wrapper, [testFile('[]', 'people.json')])
    await flushPromises()
    expect(wrapper.get('.import-profile').text()).toContain(messages.profile.jsonIntro)
    expect(wrapper.get('.import-profile').text()).toContain(messages.profile.arrays)
  })

  it('refuses a CSV whose header is not the profile, naming both sides, before uploading', async () => {
    const { wrapper, sent } = await mountImport()
    selectFiles(wrapper, [testFile('xml_id,gnd_uri,surname,forename\nS1,,Aaron,\n', 'persons.csv')])
    await waitFor(() => expect(wrapper.find('.import-error').exists()).toBe(true))

    const message = wrapper.get('.import-error').text()
    expect(message).toContain('xml:id, persName, birth, death, event, note, idno')
    expect(message).toContain('xml_id, gnd_uri, surname, forename')
    expect(wrapper.get('.import-submit').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(sent).toHaveLength(0)
  })

  it('accepts a CSV with the profile header, even after a byte-order mark', async () => {
    const { wrapper, sent } = await mountImport()
    selectFiles(wrapper, [
      testFile('﻿xml:id,persName,birth,death,event,note,idno\r\nS1,[],,,[],,[]\r\n', 'p.csv'),
    ])
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 20))
    await flushPromises()

    expect(wrapper.find('.import-error').exists()).toBe(false)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(sent).toHaveLength(1)
  })

  it('blocks submission until asynchronous CSV header validation finishes', async () => {
    const header = deferred<string>()
    const { wrapper, sent } = await mountImport()
    const file = testFile('pending', 'people.csv')
    Object.defineProperty(file, 'slice', {
      configurable: true,
      value: () => ({ text: () => header.promise }),
    })

    selectFiles(wrapper, [file])
    await flushPromises()
    expect(wrapper.get('.import-validation-status').text()).toBe(messages.upload.validatingCsv)
    expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(true)
    await wrapper.get('form').trigger('submit')
    expect(sent).toHaveLength(0)

    header.resolve('xml:id,persName,birth,death,event,note,idno\n')
    await waitFor(() =>
      expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(false),
    )
  })

  it('locks every file-selection control while the upload request is pending', async () => {
    const snapshotResponse = deferred<Response>()
    const { wrapper } = await mountImport({ snapshotResponse: snapshotResponse.promise })
    selectFiles(wrapper, [testFile('<a/>', 'a.xml')])
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    await waitFor(() => expect(wrapper.get('form').attributes('aria-busy')).toBe('true'))

    expect(wrapper.get<HTMLButtonElement>('.import-browse').element.disabled).toBe(true)
    expect(wrapper.get<HTMLInputElement>('.import-file-input').element.disabled).toBe(true)
    expect(wrapper.get<HTMLButtonElement>('.import-files-clear').element.disabled).toBe(true)
    expect(wrapper.get<HTMLButtonElement>('.import-file-remove').element.disabled).toBe(true)
    dispatchDrag(wrapper, 'drop', [testFile('{}', 'people.json')])
    await flushPromises()
    expect(wrapper.get('.import-file-item').text()).toContain('a.xml')
    expect(wrapper.get('.import-file-item').text()).not.toContain('people.json')

    snapshotResponse.resolve(jsonResponse(SNAPSHOT, { status: 202 }))
    await waitFor(() => expect(wrapper.find('.import-status-title').exists()).toBe(true))
  })

  it('refuses a file over the per-file bound before uploading', async () => {
    const { wrapper, sent } = await mountImport({ limits: { part: 4, total: 100 } })

    selectFiles(wrapper, [testFile('longer than four bytes', 'big.xml')])
    await flushPromises()

    expect(wrapper.get('main [role="alert"]').text()).toBe(messages.errors.partTooLarge)
    expect(wrapper.get('.import-submit').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(sent).toHaveLength(0)
  })

  it('refuses files that together exceed the total bound', async () => {
    const { wrapper } = await mountImport({ limits: { part: 100, total: 6 } })

    selectFiles(wrapper, [testFile('1234', 'a.xml'), testFile('5678', 'b.xml')])
    await flushPromises()

    expect(wrapper.get('main [role="alert"]').text()).toBe(messages.errors.totalTooLarge)
  })

  it('keeps empty and duplicate files visible so they can be removed', async () => {
    const { wrapper, sent } = await mountImport()

    selectFiles(wrapper, [testFile('', 'empty.xml')])
    await flushPromises()
    expect(wrapper.get('.import-file-item').text()).toContain('empty.xml')
    expect(wrapper.get('main [role="alert"]').text()).toContain(
      messages.errors.emptyFiles.replace('{names}', 'empty.xml'),
    )
    expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(true)

    await wrapper.get('.import-files-clear').trigger('click')
    await flushPromises()
    selectFiles(wrapper, [testFile('<a/>', 'same.xml'), testFile('<b/>', 'same.xml')])
    await flushPromises()
    expect(wrapper.findAll('.import-file-item')).toHaveLength(2)
    expect(wrapper.get('main [role="alert"]').text()).toContain(
      messages.errors.duplicateFiles.replace('{names}', 'same.xml'),
    )
    expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(true)
    await wrapper.get('form').trigger('submit')
    expect(sent).toHaveLength(0)
  })

  it('enforces the installation file-count limit for loose TEI', async () => {
    const { wrapper, sent } = await mountImport({
      limits: { part: 100, total: 100, members: 1 },
    })

    selectFiles(wrapper, [testFile('<a/>', 'a.xml'), testFile('<b/>', 'b.xml')])
    await flushPromises()

    expect(wrapper.findAll('.import-file-item')).toHaveLength(2)
    expect(wrapper.get('main [role="alert"]').text()).toContain(
      messages.errors.tooManyFiles.replace('{count}', '1'),
    )
    expect(wrapper.get<HTMLButtonElement>('.import-submit').element.disabled).toBe(true)
    await wrapper.get('form').trigger('submit')
    expect(sent).toHaveLength(0)
  })
})
