<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, useId, watch } from 'vue'

const props = defineProps<{
  text: string
  disabled?: boolean
  /** Label-only help belongs on the icon rail; explanations can remain available everywhere. */
  railOnly?: boolean
  desktopCollapsed?: boolean
  mobile?: boolean
}>()
const id = useId()
const open = ref(false)
const belowDesktop = ref(false)
const belowMobile = ref(false)
const enabled = computed(
  () =>
    !props.disabled &&
    (!props.railOnly ||
      (!props.mobile &&
        !belowMobile.value &&
        (belowDesktop.value || props.desktopCollapsed === true))),
)
let desktopBreakpoint: MediaQueryList | undefined
let mobileBreakpoint: MediaQueryList | undefined

function updateViewport(): void {
  belowDesktop.value = desktopBreakpoint?.matches ?? false
  belowMobile.value = mobileBreakpoint?.matches ?? false
}
const tooltip = ref<HTMLElement | null>(null)
const position = ref({ left: '0px', top: '0px' })
let trigger: HTMLElement | null = null
let focused = false
let hovered = false
let tooltipHovered = false
let dismissed = false
let closeTimer: ReturnType<typeof setTimeout> | undefined

function clearCloseTimer(): void {
  if (closeTimer !== undefined) clearTimeout(closeTimer)
  closeTimer = undefined
}

function reposition(): void {
  if (!trigger || !tooltip.value || !open.value) return
  const bounds = trigger.getBoundingClientRect()
  const popup = tooltip.value.getBoundingClientRect()
  const margin = 8
  const right = bounds.right + margin
  const left =
    right + popup.width <= window.innerWidth - margin ? right : bounds.left - popup.width - margin
  position.value = {
    left: `${Math.max(margin, Math.min(left, window.innerWidth - popup.width - margin))}px`,
    top: `${Math.max(margin, Math.min(bounds.top + (bounds.height - popup.height) / 2, window.innerHeight - popup.height - margin))}px`,
  }
}

async function show(event: Event): Promise<void> {
  clearCloseTimer()
  if (!enabled.value || dismissed) return
  if (event.currentTarget instanceof HTMLElement) trigger = event.currentTarget
  open.value = true
  await nextTick()
  reposition()
}

function scheduleClose(): void {
  clearCloseTimer()
  // Allow the pointer to cross the small gap between trigger and tooltip.
  closeTimer = setTimeout(() => {
    if (!focused && !hovered && !tooltipHovered) {
      open.value = false
      dismissed = false
    }
  }, 150)
}

function dismiss(): void {
  // Only an interaction still on the trigger needs suppression. Disabling an idle control
  // must not swallow its next fresh hover/focus when it becomes available again.
  dismissed = focused || hovered
  open.value = false
  tooltipHovered = false
  clearCloseTimer()
}

function escape(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !open.value) return
  dismiss()
  event.stopPropagation()
}

// Bind these attributes/events to the actual button, anchor, or focusable disabled destination.
// The component adds no wrapper, so the trigger keeps its own semantics and layout.
const triggerProps = computed(() => ({
  'aria-describedby': open.value ? id : undefined,
  // Native clicks include keyboard activation. Keep the tooltip dismissed while the action
  // updates its label, saves, or changes layout, even if the trigger retains hover/focus.
  onClick: dismiss,
  onMouseenter(event: MouseEvent) {
    hovered = true
    void show(event)
  },
  onMouseleave() {
    hovered = false
    scheduleClose()
  },
  onFocus(event: FocusEvent) {
    focused = true
    void show(event)
  },
  onBlur() {
    focused = false
    scheduleClose()
  },
}))

function enterTooltip(): void {
  tooltipHovered = true
  clearCloseTimer()
}

function leaveTooltip(): void {
  tooltipHovered = false
  scheduleClose()
}

watch(enabled, (canShow) => {
  if (!canShow) dismiss()
})
watch(
  () => props.text,
  async () => {
    await nextTick()
    reposition()
  },
)

onMounted(() => {
  desktopBreakpoint = window.matchMedia('(width < 1080px)')
  mobileBreakpoint = window.matchMedia('(width < 720px)')
  updateViewport()
  desktopBreakpoint.addEventListener('change', updateViewport)
  mobileBreakpoint.addEventListener('change', updateViewport)
  document.addEventListener('keydown', escape, true)
  window.addEventListener('resize', reposition)
  window.addEventListener('scroll', reposition, true)
})
onUnmounted(() => {
  clearCloseTimer()
  desktopBreakpoint?.removeEventListener('change', updateViewport)
  mobileBreakpoint?.removeEventListener('change', updateViewport)
  if (typeof document !== 'undefined') document.removeEventListener('keydown', escape, true)
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', reposition)
    window.removeEventListener('scroll', reposition, true)
  }
})
</script>

<template>
  <slot :trigger-props="triggerProps" />
  <Teleport to="body">
    <!-- The trigger owns keyboard interaction. A tooltip must remain hoverable without becoming a tab stop. -->
    <!-- eslint-disable vuejs-accessibility/mouse-events-have-key-events, vuejs-accessibility/no-static-element-interactions -->
    <div
      v-if="open"
      :id="id"
      ref="tooltip"
      role="tooltip"
      class="sidebar-tooltip"
      :style="position"
      @mouseenter="enterTooltip"
      @mouseleave="leaveTooltip"
    >
      {{ text }}
    </div>
    <!-- eslint-enable vuejs-accessibility/mouse-events-have-key-events, vuejs-accessibility/no-static-element-interactions -->
  </Teleport>
</template>

<style scoped>
.sidebar-tooltip {
  position: fixed;
  z-index: 100;
  max-width: min(18rem, calc(100vw - var(--space-4)));
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  background: var(--text-primary);
  color: var(--panel);
  font-size: var(--font-size-body-strong);
  line-height: var(--line-height-body-strong);
  overflow-wrap: anywhere;
}
</style>
