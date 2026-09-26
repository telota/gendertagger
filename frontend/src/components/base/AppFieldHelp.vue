<script setup lang="ts">
import { PhInfo } from '@phosphor-icons/vue'
import { nextTick, onMounted, onUnmounted, ref, useId, watch } from 'vue'

// The field references descriptionId, so its constraints remain available to screen readers
// without needing to discover or activate the help button.
const props = defineProps<{ descriptionId: string; label: string; text: string }>()
const tooltipId = useId()
const trigger = ref<HTMLButtonElement | null>(null)
const tooltip = ref<HTMLElement | null>(null)
const open = ref(false)
const position = ref({ left: '0px', top: '0px' })
let focused = false
let hovered = false
let tooltipHovered = false
let pinned = false
let dismissed = false
let closeTimer: ReturnType<typeof setTimeout> | undefined

function clearCloseTimer(): void {
  if (closeTimer !== undefined) clearTimeout(closeTimer)
  closeTimer = undefined
}

function reposition(): void {
  if (!trigger.value || !tooltip.value || !open.value) return
  const anchor = trigger.value.getBoundingClientRect()
  const popup = tooltip.value.getBoundingClientRect()
  const margin = 8
  const below = anchor.bottom + margin
  const top =
    below + popup.height <= window.innerHeight - margin ? below : anchor.top - popup.height - margin
  position.value = {
    left: `${Math.max(margin, Math.min(anchor.right - popup.width, window.innerWidth - popup.width - margin))}px`,
    top: `${Math.max(margin, top)}px`,
  }
}

async function show(): Promise<void> {
  clearCloseTimer()
  if (dismissed) return
  open.value = true
  await nextTick()
  reposition()
}

function scheduleClose(): void {
  clearCloseTimer()
  // Let the pointer cross the gap so the explanatory text can itself be hovered.
  closeTimer = setTimeout(() => {
    if (!focused && !hovered && !tooltipHovered && !pinned) {
      open.value = false
      dismissed = false
    }
  }, 150)
}

function dismiss(): void {
  clearCloseTimer()
  open.value = false
  pinned = false
  tooltipHovered = false
  dismissed = focused || hovered
}

function toggle(): void {
  if (pinned) dismiss()
  else {
    // A tap may focus the button before its click. Pin the already-visible help instead of
    // immediately closing it; a second tap dismisses it.
    pinned = true
    dismissed = false
    void show()
  }
}

function enterTrigger(): void {
  hovered = true
  void show()
}
function leaveTrigger(): void {
  hovered = false
  scheduleClose()
}
function focusTrigger(): void {
  focused = true
  void show()
}
function blurTrigger(): void {
  focused = false
  pinned = false
  scheduleClose()
}
function enterTooltip(): void {
  tooltipHovered = true
  clearCloseTimer()
}
function leaveTooltip(): void {
  tooltipHovered = false
  scheduleClose()
}
function escape(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !open.value) return
  dismiss()
  event.stopPropagation()
}
function outside(event: PointerEvent): void {
  if (!(event.target instanceof Node)) return
  if (!trigger.value?.contains(event.target) && !tooltip.value?.contains(event.target)) dismiss()
}

watch(
  () => props.text,
  async () => {
    await nextTick()
    reposition()
  },
)

onMounted(() => {
  document.addEventListener('keydown', escape, true)
  document.addEventListener('pointerdown', outside, true)
  window.addEventListener('resize', reposition)
  window.addEventListener('scroll', reposition, true)
})
onUnmounted(() => {
  clearCloseTimer()
  document.removeEventListener('keydown', escape, true)
  document.removeEventListener('pointerdown', outside, true)
  window.removeEventListener('resize', reposition)
  window.removeEventListener('scroll', reposition, true)
})
</script>

<template>
  <span :id="descriptionId" class="app-field-help-description">{{ text }}</span>
  <button
    ref="trigger"
    class="app-field-help"
    type="button"
    :aria-label="label"
    :aria-describedby="open ? tooltipId : undefined"
    @mouseenter="enterTrigger"
    @mouseleave="leaveTrigger"
    @focus="focusTrigger"
    @blur="blurTrigger"
    @click="toggle"
  >
    <PhInfo :size="20" aria-hidden="true" />
  </button>
  <Teleport to="body">
    <!-- The trigger provides keyboard interaction; the tooltip stays hoverable without a tab stop. -->
    <!-- eslint-disable vuejs-accessibility/mouse-events-have-key-events, vuejs-accessibility/no-static-element-interactions -->
    <div
      v-if="open"
      :id="tooltipId"
      ref="tooltip"
      role="tooltip"
      class="app-field-help-tooltip"
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
.app-field-help-description {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

.app-field-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  inline-size: var(--control-min-size);
  block-size: var(--control-min-size);
  padding: 0;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.app-field-help:hover {
  color: var(--accent);
}
.app-field-help-tooltip {
  position: fixed;
  z-index: 100;
  max-inline-size: min(22rem, calc(100vw - var(--space-4)));
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  background: var(--text-primary);
  color: var(--panel);
  font-size: var(--font-size-body-strong);
  line-height: var(--line-height-body-strong);
  overflow-wrap: anywhere;
}
</style>
