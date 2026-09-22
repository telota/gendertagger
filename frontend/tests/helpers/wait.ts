import { flushPromises } from '@vue/test-utils'

/**
 * Poll `assertion` until it stops throwing, or fail with its last error after `timeoutMs`.
 *
 * A single `flushPromises()` flushes one macrotask, which is enough once a route's component has
 * already been dynamically imported in this process. The *first* import of a given lazy route (any
 * navigation away from the route `mountApplicationAt` started on, to a route not yet visited in this
 * test file) needs more than one macrotask tick to resolve, so a fixed-count flush is unreliable;
 * this polls instead of guessing a tick count.
 */
export async function waitFor(assertion: () => void, timeoutMs = 2000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    await flushPromises()
    try {
      assertion()
      return
    } catch (error) {
      if (Date.now() >= deadline) throw error
    }
  }
}
