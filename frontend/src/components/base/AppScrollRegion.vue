<script setup lang="ts">
import { onBeforeUnmount, onMounted, onUpdated, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'

defineProps<{ label: string }>()

const { t } = useI18n()
const hintId = useId()
const viewport = ref<HTMLElement | null>(null)
const content = ref<HTMLElement | null>(null)
const overflows = ref(false)
let observer: ResizeObserver | undefined
const observedRoots = new Set<Element>()

function measureOverflow(): void {
  const element = viewport.value
  if (element === null) return
  overflows.value = element.scrollWidth > element.clientWidth + 1
}

function observeContentRoots(): void {
  if (observer === undefined || content.value === null) return
  const roots = new Set(content.value.children)
  for (const previous of observedRoots) {
    if (!roots.has(previous)) {
      observer.unobserve(previous)
      observedRoots.delete(previous)
    }
  }
  for (const element of roots) {
    if (!observedRoots.has(element)) {
      observer.observe(element)
      observedRoots.add(element)
    }
  }
}

onMounted(() => {
  observer = new ResizeObserver(measureOverflow)
  if (viewport.value !== null) observer.observe(viewport.value)
  if (content.value !== null) observer.observe(content.value)
  observeContentRoots()
  measureOverflow()
})

// Observe slotted tables as well: fonts and descendant updates can change their width while the
// wrapper stays the same size. Reconcile roots when loading replaces the slotted content.
onUpdated(() => {
  observeContentRoots()
  measureOverflow()
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div class="app-scroll-frame">
    <div
      ref="viewport"
      class="app-scroll-region"
      role="region"
      :aria-label="label"
      :aria-describedby="overflows ? hintId : undefined"
      :tabindex="overflows ? 0 : undefined"
    >
      <div ref="content" class="app-scroll-content"><slot /></div>
    </div>
    <p v-if="overflows" :id="hintId" class="app-scroll-hint">
      {{ t('layout.horizontalScrollHint') }}
    </p>
  </div>
</template>

<style scoped>
.app-scroll-frame,
.app-scroll-region,
.app-scroll-content {
  min-inline-size: 0;
  max-inline-size: 100%;
}

.app-scroll-region {
  overflow-x: auto;
}

.app-scroll-hint {
  margin: var(--space-2) 0 0;
  padding-inline: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}
</style>
