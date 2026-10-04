import { unwrap, type ApiClient, type components } from '@/api'

import type { ExportFormat } from './useExports'

type ExportManifestOutput = components['schemas']['ExportManifestOutput']
type ExportManifest = components['schemas']['ExportManifest']

const SHA256 = /^[0-9a-f]{64}$/

function str(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

/** A manifest, or `null` for anything else (an ordinary output such as a JSON result bundle). */
function parseExportManifest(text: string, exportId: string): ExportManifest | null {
  let body: unknown
  try {
    body = JSON.parse(text)
  } catch {
    return null
  }
  if (typeof body !== 'object' || body === null || Array.isArray(body)) return null
  const m = body as Record<string, unknown>
  if (m['version'] !== 1 || m['export_execution_id'] !== exportId) return null
  const outputs = m['outputs']
  if (!Array.isArray(outputs) || outputs.length === 0) return null

  const parsedOutputs: ExportManifestOutput[] = []
  for (const raw of outputs) {
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return null
    const o = raw as Record<string, unknown>
    const sha = str(o['sha256'])
    const name = str(o['logical_name'])
    const media = str(o['media_type'])
    const size = o['byte_size']
    if (
      !sha ||
      !SHA256.test(sha) ||
      !name ||
      !media ||
      typeof size !== 'number' ||
      !Number.isInteger(size) ||
      size < 0
    ) {
      return null
    }
    parsedOutputs.push({
      logical_name: name,
      sha256: sha,
      byte_size: size,
      media_type: media,
    })
  }

  const source = str(m['source_snapshot_sha256'])
  const snapshot = str(m['dataset_snapshot_id'])
  const run = str(m['run_id'])
  const aggregation = str(m['aggregation_execution_id'])
  const format = m['format']
  const policy = m['label_source_policy']
  const profile = m['tei_profile']
  const generated = str(m['generated_at'])
  if (
    !source ||
    !SHA256.test(source) ||
    !snapshot ||
    !run ||
    !aggregation ||
    (format !== 'tei' && format !== 'json' && format !== 'csv') ||
    (policy !== 'machine_aggregation' && policy !== 'human_overrides') ||
    (profile !== undefined && profile !== null && profile !== 'tei_p5_gender_v1') ||
    !generated
  ) {
    return null
  }
  return {
    version: 1,
    export_execution_id: exportId,
    dataset_snapshot_id: snapshot,
    source_snapshot_sha256: source,
    run_id: run,
    aggregation_execution_id: aggregation,
    format,
    label_source_policy: policy,
    tei_profile: profile ?? null,
    outputs: parsedOutputs,
    generated_at: generated,
  }
}

/** Lower-case hex SHA-256 of some bytes, computed in the browser (Web Crypto). */
async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

export interface DownloadedExport {
  blob: Blob
  filename: string
  mediaType: string
  byteSize: number
  /** Checksum of exactly the bytes that were downloaded. */
  sha256: string
  /** Set when the server answered with the manifest instead of a single output. */
  manifest: ExportManifest | null
}

const EXTENSION: Record<ExportFormat, string> = { tei: 'xml', json: 'json', csv: 'csv' }

function filenameFrom(response: Response, fallback: string): string {
  const header = response.headers.get('content-disposition') ?? ''
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header)
  return match?.[1] ? decodeURIComponent(match[1]) : fallback
}

/**
 * `GET /exports/{id}/download`: the export's own output when it produced exactly one, otherwise the
 * manifest (docs/08). The bytes are hashed here so the reader can compare the checksum with the one
 * recorded by `GET /exports/{id}/manifest` or the download's `X-Checksum-SHA256` header.
 */
export async function downloadExport(
  client: ApiClient,
  exportId: string,
  format: ExportFormat,
  signal?: AbortSignal,
): Promise<DownloadedExport> {
  const pending = client.GET('/api/v1/exports/{export_execution_id}/download', {
    params: { path: { export_execution_id: exportId } },
    parseAs: 'blob',
    ...(signal ? { signal } : {}),
  })
  const blob = await unwrap(pending)
  const { response } = await pending
  const buffer = await blob.arrayBuffer()
  const mediaType = response.headers.get('content-type') ?? blob.type
  const manifest = mediaType.includes('json')
    ? parseExportManifest(new TextDecoder().decode(buffer), exportId)
    : null
  const fallback = manifest ? 'manifest.json' : `export-${exportId}.${EXTENSION[format]}`
  return {
    blob,
    filename: filenameFrom(response, fallback),
    mediaType,
    byteSize: buffer.byteLength,
    sha256: await sha256Hex(buffer),
    manifest,
  }
}

/** Hand the bytes to the browser as a file download. */
export function saveDownload(download: DownloadedExport): void {
  const url = URL.createObjectURL(download.blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = download.filename
  try {
    document.body.appendChild(anchor)
    anchor.click()
  } finally {
    anchor.remove()
    URL.revokeObjectURL(url)
  }
}
