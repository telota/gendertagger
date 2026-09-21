import createClient, { type Client, type Middleware } from 'openapi-fetch'

import { CSRF_HEADER_NAME, isUnsafeMethod, readCsrfToken } from './csrf'
import { networkError, parseApiError } from './errors'
import type { paths } from './schema'

export type ApiClient = Client<paths>

export interface ApiClientOptions {
  /** Custom `fetch`, used by tests to keep the network at the transport boundary. */
  fetch?: (request: Request) => Promise<Response>
  /** Source of the CSRF token; defaults to the provisional cookie convention. */
  csrfToken?: () => string | null
}

function defaultCsrfToken(): string | null {
  return readCsrfToken(document.cookie)
}

/**
 * Create the one typed HTTP client of the application.
 *
 * Requests carry the session cookie (`credentials: 'include'`) and, for every unsafe method, the CSRF
 * header. No call site opts out of either.
 */
export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const csrfToken = options.csrfToken ?? defaultCsrfToken
  const client = createClient<paths>({
    // Every path in the generated schema already starts with `/api/v1`, and the deployment is
    // same-origin, so the base is the page's own origin, spelled out because a `Request` needs an
    // absolute URL outside a browser.
    baseUrl: window.location.origin,
    credentials: 'include',
    ...(options.fetch === undefined ? {} : { fetch: options.fetch }),
  })

  const attachCsrfToken: Middleware = {
    onRequest({ request }) {
      if (isUnsafeMethod(request.method)) {
        const token = csrfToken()
        if (token !== null) request.headers.set(CSRF_HEADER_NAME, token)
      }
      return request
    },
  }
  client.use(attachCsrfToken)
  return client
}

type Settled<T> =
  | { data: T; error?: never; response: Response }
  | { data?: never; error: unknown; response: Response }

/**
 * Resolve a typed client call to its data, or throw a classified `ApiError`.
 *
 * A rejected `fetch` becomes `network_error`; a non-success response is parsed centrally from the
 * shared error envelope. An aborted request rethrows untouched so a superseded query stays silent.
 */
export async function unwrap<T>(pending: PromiseLike<Settled<T>>): Promise<T> {
  let settled: Settled<T>
  try {
    settled = await pending
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw networkError(cause)
  }
  if (settled.error !== undefined) {
    throw parseApiError(settled.response.status, settled.error, settled.response.headers)
  }
  // openapi-fetch reports either `data` or `error`. A 204 carries neither, and `T` is then the
  // operation's no-content type, which the compiler cannot see through the optional union member.
  return settled.data as T
}
