import type { components } from './schema'

export type ApiErrorDetail = components['schemas']['ApiErrorDetail']
export type ApiErrorEnvelope = components['schemas']['ApiErrorEnvelope']
type ErrorDetails = NonNullable<ApiErrorDetail['details']>

/**
 * Codes that the client itself assigns when no server envelope is available.
 *
 * Server codes are an open vocabulary owned by the backend (`annotation_conflict`,
 * `payload_too_large`, ...); these two never collide with them because the server never sends them.
 */
export const CLIENT_ERROR_CODES = {
  networkError: 'network_error',
  unparseableResponse: 'unparseable_response',
} as const

export type ClientErrorCode = (typeof CLIENT_ERROR_CODES)[keyof typeof CLIENT_ERROR_CODES]

export const REQUEST_ID_HEADER = 'x-request-id'

/** One failed API interaction, selected by its stable `code` and never by its message text. */
export class ApiError extends Error {
  readonly status: number | null
  readonly code: string
  readonly details: ErrorDetails
  readonly requestId: string | null

  constructor(init: {
    status: number | null
    code: string
    message: string
    details?: ErrorDetails
    requestId?: string | null
    cause?: unknown
  }) {
    super(init.message, init.cause === undefined ? undefined : { cause: init.cause })
    this.name = 'ApiError'
    this.status = init.status
    this.code = init.code
    this.details = init.details ?? {}
    this.requestId = init.requestId ?? null
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Narrow an untrusted response body to the shared error envelope. */
export function isApiErrorEnvelope(body: unknown): body is ApiErrorEnvelope {
  if (!isRecord(body) || !isRecord(body.error)) return false
  return typeof body.error.code === 'string' && typeof body.error.message === 'string'
}

/**
 * Build an {@link ApiError} from a non-success response.
 *
 * A body that is not the shared envelope (a proxy error page, for example) keeps its HTTP status but
 * receives the client-side `unparseable_response` code, so callers never match on raw text.
 */
export function parseApiError(status: number, body: unknown, headers: Headers): ApiError {
  const headerRequestId = headers.get(REQUEST_ID_HEADER)
  if (isApiErrorEnvelope(body)) {
    const { code, message, details, request_id: requestId } = body.error
    return new ApiError({
      status,
      code,
      message,
      ...(details === undefined ? {} : { details }),
      requestId: requestId ?? headerRequestId,
    })
  }
  return new ApiError({
    status,
    code: CLIENT_ERROR_CODES.unparseableResponse,
    message: `The server answered ${status} without a recognisable error envelope.`,
    requestId: headerRequestId,
  })
}

/** Wrap a rejected `fetch`, which means the server was never reached. */
export function networkError(cause: unknown): ApiError {
  return new ApiError({
    status: null,
    code: CLIENT_ERROR_CODES.networkError,
    message: 'The server could not be reached.',
    cause,
  })
}
