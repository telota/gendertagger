import { ref, type Ref } from 'vue'

interface Waiter {
  resolve: () => void
  reject: (reason: unknown) => void
}

// Shared app-wide state, deliberately module-scoped like `useTheme`'s `preference`: there is exactly
// one recovery prompt for the whole page, and it is triggered from outside any component (the API
// client's `onUnauthorized` hook), not from a particular component instance.
const isOpen = ref(false)
const waiters: Waiter[] = []

/**
 * Ask the user to sign in again without leaving the page they were on (decision D1). Requests that hit
 * a `401` around the same moment share a single prompt and are settled together once it closes.
 */
export function requestReauthentication(): Promise<void> {
  isOpen.value = true
  return new Promise((resolve, reject) => {
    waiters.push({ resolve, reject })
  })
}

export interface UseSessionRecovery {
  isOpen: Ref<boolean>
  /** Call once the user has successfully signed in again; retries every waiting request. */
  resolve: () => void
  /** Call if the user declines instead of signing in; every waiting request gives up. */
  reject: (reason: unknown) => void
}

export function useSessionRecovery(): UseSessionRecovery {
  function settle(settleOne: (waiter: Waiter) => void): void {
    isOpen.value = false
    const pending = waiters.splice(0, waiters.length)
    for (const waiter of pending) settleOne(waiter)
  }

  function resolve(): void {
    settle((waiter) => {
      waiter.resolve()
    })
  }

  function reject(reason: unknown): void {
    settle((waiter) => {
      waiter.reject(reason)
    })
  }

  return { isOpen, resolve, reject }
}
