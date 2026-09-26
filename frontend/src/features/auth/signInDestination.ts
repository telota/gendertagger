import type { RouteLocationRaw } from 'vue-router'

/**
 * Where a page-level sign-in continues once it has succeeded: the forced password change when the
 * session requires it (carrying `target` along so it can finish the journey), otherwise `target`.
 * `target` is a same-origin path, never an external URL.
 */
export function signInDestination(mustChangePassword: boolean, target: string): RouteLocationRaw {
  return mustChangePassword ? { name: 'changePassword', query: { redirect: target } } : target
}
