import { onScopeDispose, ref, watch, type Ref } from 'vue'

/** Keep an input value stable until the caller's debounce window has elapsed. */
export function useDebouncedValue<T>(source: Ref<T>, delayMs: number): Ref<T> {
  const debounced = ref(source.value) as Ref<T>
  let timer: ReturnType<typeof setTimeout> | undefined

  watch(source, (value) => {
    if (timer !== undefined) clearTimeout(timer)
    timer = setTimeout(() => {
      debounced.value = value
      timer = undefined
    }, delayMs)
  })

  onScopeDispose(() => {
    clearTimeout(timer)
  })

  return debounced
}
