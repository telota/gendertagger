import { nextTick, onScopeDispose, type Ref } from 'vue'
import { START_LOCATION, useRouter } from 'vue-router'

/** Move into a new page once, without disturbing in-page state or a modal's focus ownership. */
export function useRouteFocus(content: Ref<HTMLElement | null>): void {
  const router = useRouter()
  let revision = 0
  let frame: number | undefined

  function cancelPending(): void {
    revision += 1
    if (frame !== undefined) cancelAnimationFrame(frame)
    frame = undefined
  }

  const removeHook = router.afterEach((to, from, failure) => {
    // Bootstrap mounts before the first navigation settles. Query/hash updates represent filters,
    // selected records or anchors within the current page, so those retain the caller's focus.
    if (failure || from === START_LOCATION) return
    if (to.path === from.path) {
      // Query hydration may follow page entry automatically. Preserve that pending transfer unless
      // the user is already working in the new content and owns focus there.
      if (content.value?.contains(document.activeElement)) cancelPending()
      return
    }
    cancelPending()
    const scheduledRevision = revision
    void nextTick(() => {
      if (scheduledRevision !== revision) return
      // Let Headless UI close menus/drawers and restore their triggers before moving into the page.
      frame = requestAnimationFrame(() => {
        frame = undefined
        if (scheduledRevision !== revision || router.currentRoute.value.path !== to.path) return
        const target = content.value
        if (target === null || !target.isConnected) return
        if (
          document.querySelector(
            '[role="dialog"][aria-modal="true"], [role="alertdialog"][aria-modal="true"], dialog[open]',
          )
        )
          return
        // This stable wrapper exists during loading and failure too. A later heading or data update
        // must never cause a second focus transfer while the user has already started working.
        target.focus()
      })
    })
  })

  onScopeDispose(() => {
    removeHook()
    cancelPending()
  })
}
