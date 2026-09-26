import {
  computed,
  inject,
  onScopeDispose,
  provide,
  ref,
  watch,
  type InjectionKey,
  type Ref,
} from 'vue'
import { useRouter, type RouteLocationNormalized } from 'vue-router'

import { useSessionStore } from '@/stores/session'

type Draft = { dirty: () => boolean; discard: () => void }

interface DraftNavigation {
  isOpen: Ref<boolean>
  confirmLeave: () => Promise<boolean>
  resolveLeave: (leave: boolean) => void
  discardDrafts: () => void
  register: (draft: Draft) => () => void
}

const draftNavigationKey: InjectionKey<DraftNavigation> = Symbol('draft-navigation')

/** Install one registry per application; the registry stores callbacks, never draft contents. */
export function provideDraftNavigation(): DraftNavigation {
  const router = useRouter()
  const session = useSessionStore()
  const isOpen = ref(false)
  const drafts = new Set<Draft>()
  const principal = computed(() => session.user?.id ?? null)
  let pending: Promise<boolean> | undefined
  let finish: ((leave: boolean) => void) | undefined

  function resolveLeave(leave: boolean): void {
    isOpen.value = false
    const resolve = finish
    pending = undefined
    finish = undefined
    resolve?.(leave)
  }

  function discardDrafts(): void {
    for (const draft of drafts) draft.discard()
  }

  function confirmLeave(): Promise<boolean> {
    if (pending !== undefined) return pending
    if (![...drafts].some((draft) => draft.dirty())) return Promise.resolve(true)
    isOpen.value = true
    pending = new Promise<boolean>((resolve) => {
      finish = resolve
    })
    return pending
  }

  const navigation: DraftNavigation = {
    isOpen,
    confirmLeave,
    resolveLeave,
    discardDrafts,
    register(draft) {
      drafts.add(draft)
      return () => drafts.delete(draft)
    },
  }
  provide(draftNavigationKey, navigation)

  const approved = new WeakMap<RouteLocationNormalized, Draft[]>()
  const removeGuard = router.beforeEach(async (to, from) => {
    // Evidence workbenches select a person in the query; raw annotation uses a path parameter.
    // Filter-only changes keep the same mounted person's draft and do not need confirmation.
    const personChanged =
      (from.name === 'review' || from.name === 'people') &&
      JSON.stringify(to.query.person ?? null) !== JSON.stringify(from.query.person ?? null)
    if (to.path === from.path && !personChanged) return true
    const forcedAuthentication =
      (to.name === 'login' && !session.isSignedIn) ||
      (to.name === 'changePassword' && session.mustChangePassword)
    const leave = forcedAuthentication || (await confirmLeave())
    if (leave) approved.set(to, [...drafts])
    return leave
  })
  const removeAfterGuard = router.afterEach((to, _from, failure) => {
    // A later guard can still reject the navigation after the user agreed to leave.
    if (failure === undefined) approved.get(to)?.forEach((draft) => draft.discard())
    approved.delete(to)
  })

  // A changed identity must never inherit another account's input or an outstanding leave decision.
  watch(
    principal,
    () => {
      discardDrafts()
      resolveLeave(false)
    },
    { flush: 'sync' },
  )

  onScopeDispose(() => {
    removeGuard()
    removeAfterGuard()
    resolveLeave(false)
    drafts.clear()
  })
  return navigation
}

/** Menus can ask before a mutation; confirmation alone never discards input. */
export function useDraftNavigation(): Pick<
  DraftNavigation,
  'isOpen' | 'confirmLeave' | 'resolveLeave' | 'discardDrafts'
> {
  return (
    inject(draftNavigationKey, null) ?? {
      isOpen: ref(false),
      confirmLeave: () => Promise.resolve(true),
      resolveLeave: () => undefined,
      discardDrafts: () => undefined,
    }
  )
}

/** Register a view-owned draft and release its callbacks when that view leaves the application. */
export function useDraftRegistration(dirty: () => boolean, discard: () => void): void {
  const navigation = inject(draftNavigationKey, null)
  if (navigation === null) return
  const unregister = navigation.register({ dirty, discard })
  onScopeDispose(unregister)
}
