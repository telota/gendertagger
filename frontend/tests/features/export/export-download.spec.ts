import { webcrypto } from 'node:crypto'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { createApiClient } from '@/api'
import { downloadExport, parseExportManifest, sha256Hex } from '@/features/export/exportDownload'

import realManifest from './fixtures/seed-manifest.json'

const ID = 'e2000000-0000-0000-0000-000000000001'
const manifest = () => ({
  version: 1,
  export_execution_id: ID,
  dataset_snapshot_id: 'c0000000-0000-0000-0000-000000000001',
  source_snapshot_sha256: 'a'.repeat(64),
  run_id: 'd0000000-0000-0000-0000-000000000001',
  aggregation_execution_id: 'f0000000-0000-0000-0000-000000000001',
  format: 'tei',
  label_source_policy: 'human_overrides',
  tei_profile: 'tei_p5_gender_v1',
  outputs: [
    {
      logical_name: 'a.xml',
      sha256: 'b'.repeat(64),
      byte_size: 1,
      media_type: 'application/tei+xml',
    },
  ],
  generated_at: '2026-01-01T00:00:00Z',
})

beforeEach(() => {
  vi.stubGlobal('crypto', webcrypto)
})

describe('sha256Hex', () => {
  it('matches the well-known digest of "abc"', async () => {
    const bytes = new TextEncoder().encode('abc')

    expect(await sha256Hex(bytes.buffer as ArrayBuffer)).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    )
  })
})

describe('parseExportManifest', () => {
  it('reads a manifest of this export', () => {
    const parsed = parseExportManifest(JSON.stringify(manifest()), ID)

    expect(parsed?.source_snapshot_sha256).toBe('a'.repeat(64))
    expect(parsed?.outputs[0]?.logical_name).toBe('a.xml')
  })

  it('keeps nullable profile defaults and zero-byte outputs', () => {
    const body: Record<string, unknown> = {
      ...manifest(),
      format: 'json',
      outputs: [{ ...manifest().outputs[0], byte_size: 0 }],
    }
    delete body['tei_profile']

    expect(parseExportManifest(JSON.stringify(body), ID)?.tei_profile).toBeNull()
    expect(parseExportManifest(JSON.stringify(body), ID)?.outputs[0]?.byte_size).toBe(0)
    expect(
      parseExportManifest(JSON.stringify({ ...body, tei_profile: null }), ID)?.tei_profile,
    ).toBeNull()
  })

  it.each([
    ['a JSON result bundle (an array)', JSON.stringify([{ tei_id: 'x' }])],
    ['text that is not JSON', '<TEI/>'],
    [
      'a manifest of another export',
      JSON.stringify({ ...manifest(), export_execution_id: 'other' }),
    ],
    ['an unknown manifest version', JSON.stringify({ ...manifest(), version: 2 })],
    ['a manifest with no outputs', JSON.stringify({ ...manifest(), outputs: [] })],
    [
      'an output with a malformed checksum',
      JSON.stringify({ ...manifest(), outputs: [{ ...manifest().outputs[0], sha256: 'xyz' }] }),
    ],
    [
      'a source hash that is not a checksum',
      JSON.stringify({ ...manifest(), source_snapshot_sha256: 'nope' }),
    ],
    ['an unsupported format', JSON.stringify({ ...manifest(), format: 'pdf' })],
    [
      'an unsupported label policy',
      JSON.stringify({ ...manifest(), label_source_policy: 'other' }),
    ],
    ['an unsupported profile', JSON.stringify({ ...manifest(), tei_profile: 'other' })],
    ['an incorrectly shaped profile', JSON.stringify({ ...manifest(), tei_profile: {} })],
    [
      'a negative output size',
      JSON.stringify({ ...manifest(), outputs: [{ ...manifest().outputs[0], byte_size: -1 }] }),
    ],
    [
      'a fractional output size',
      JSON.stringify({ ...manifest(), outputs: [{ ...manifest().outputs[0], byte_size: 0.5 }] }),
    ],
    ['an array instead of an output', JSON.stringify({ ...manifest(), outputs: [[]] })],
  ])('does not take %s for a manifest', (_name, text) => {
    expect(parseExportManifest(text, ID)).toBeNull()
  })
})

describe('downloadExport', () => {
  it.each<[string, string, boolean]>([
    ['a single JSON output', '{ "records": [] }\n', false],
    ['a manifest', JSON.stringify(manifest(), null, 2) + '\n', true],
  ])('retains the exact bytes and checksum of %s', async (_name, text, isManifest) => {
    const bytes = new TextEncoder().encode(text)
    const client = createApiClient({
      fetch: async () =>
        new Response(bytes, {
          headers: {
            'content-type': 'application/json',
            'content-disposition': 'attachment; filename="stored.json"',
          },
        }),
    })

    const downloaded = await downloadExport(client, ID, 'json')

    expect(Array.from(new Uint8Array(await downloaded.blob.arrayBuffer()))).toEqual(
      Array.from(bytes),
    )
    expect(downloaded.sha256).toBe(await sha256Hex(bytes.buffer))
    expect(downloaded.byteSize).toBe(bytes.byteLength)
    expect(downloaded.mediaType).toBe('application/json')
    expect(downloaded.filename).toBe('stored.json')
    expect(downloaded.manifest !== null).toBe(isManifest)
  })
})

// The manifest the real backend wrote for the seeded export: the checksum in it is the SHA-256 of the
// bytes the download returns (checked when it was captured), so it is the contract for verification.
describe('a manifest as the real backend stored it', () => {
  it('parses, and records the checksum and size of the output', () => {
    const parsed = parseExportManifest(
      JSON.stringify(realManifest),
      realManifest.export_execution_id,
    )

    expect(parsed?.outputs).toEqual([
      {
        logical_name: 'export.json',
        sha256: 'f9c5d652d14b8e205b845e0d0c8b815b3ef85a7eb0934cbfa285ec6f0438167e',
        byte_size: 2323,
        media_type: 'application/json',
      },
    ])
    expect(parsed?.label_source_policy).toBe('human_overrides')
    expect(parsed?.tei_profile).toBeNull()
  })
})
