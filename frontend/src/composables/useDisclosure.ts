import { nextTick, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

/** The caller owns context and access policy; ordinary collapse retains the mounted content. */
export function useDisclosure(options: {
  resetKey: MaybeRefOrGetter<readonly unknown[]>
  canRetain: MaybeRefOrGetter<boolean>
  focusHeading: () => void
}) {
  const isOpen = ref(false)
  const hasMounted = ref(false)
  let revision = 0

  function reset(): void {
    revision += 1
    isOpen.value = false
    hasMounted.value = false
  }

  async function toggle(): Promise<void> {
    if (!toValue(options.canRetain)) return
    isOpen.value = !isOpen.value
    if (!isOpen.value) return
    hasMounted.value = true
    const openingRevision = revision
    await nextTick()
    if (openingRevision === revision && isOpen.value) options.focusHeading()
  }

  watch(() => toValue(options.resetKey), reset, { flush: 'sync' })
  watch(
    () => toValue(options.canRetain),
    (canRetain) => {
      if (!canRetain) reset()
    },
    { flush: 'sync' },
  )

  return { isOpen, hasMounted, toggle }
}
