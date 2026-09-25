<script setup lang="ts">
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { PhX } from '@phosphor-icons/vue'
import { onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { useSessionStore } from '@/stores/session'

import AppSidebar from './AppSidebar.vue'

const open = defineModel<boolean>({ required: true })
const { t } = useI18n()
const route = useRoute()
const session = useSessionStore()
let mobileQuery: MediaQueryList | null = null
let focusFrame: number | undefined

function close(): void {
  open.value = false
}

function handleBreakpoint(event: MediaQueryListEvent): void {
  if (event.matches || !open.value) return
  close()
  // The drawer's trigger becomes hidden at this breakpoint. After Dialog restores focus,
  // move it to the equivalent visible destination instead of leaving it on the document body.
  focusFrame = requestAnimationFrame(() => {
    if (open.value) return
    const current = document.querySelector<HTMLElement>(
      '.app-shell > .app-sidebar [aria-current="page"]',
    )
    const brand = document.querySelector<HTMLElement>(
      '.app-shell > .app-sidebar .app-sidebar-brand',
    )
    const target = current ?? brand
    target?.focus()
  })
}

// A confirmed route change closes the drawer; a cancelled/failed navigation leaves it open.
watch(() => route.fullPath, close)
watch(() => [session.user?.id, session.canUsePrivateNavigation], close)

onMounted(() => {
  mobileQuery = window.matchMedia('(width < 720px)')
  mobileQuery.addEventListener('change', handleBreakpoint)
})

onUnmounted(() => {
  mobileQuery?.removeEventListener('change', handleBreakpoint)
  if (focusFrame !== undefined) cancelAnimationFrame(focusFrame)
})
</script>

<template>
  <Dialog :open="open" class="mobile-navigation" @close="close">
    <div class="mobile-navigation-backdrop" aria-hidden="true" />
    <div class="mobile-navigation-frame">
      <DialogPanel class="mobile-navigation-panel">
        <div class="mobile-navigation-heading">
          <DialogTitle class="mobile-navigation-title">{{ t('nav.label') }}</DialogTitle>
          <button
            type="button"
            class="mobile-navigation-close"
            :aria-label="t('nav.closeNavigation')"
            @click="close"
          >
            <PhX :size="24" aria-hidden="true" />
          </button>
        </div>
        <AppSidebar mobile />
      </DialogPanel>
    </div>
  </Dialog>
</template>

<style scoped>
/* Dialog portals its root without Vue's scope attribute; keep this unique root selector global. */
:global(.mobile-navigation) {
  position: fixed;
  inset: 0;
  z-index: 30;
}

.mobile-navigation-backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
}

.mobile-navigation-frame {
  position: fixed;
  inset: 0;
  display: flex;
}

.mobile-navigation-panel {
  display: flex;
  flex-direction: column;
  width: min(20rem, calc(100% - var(--space-10)));
  height: 100dvh;
  background: var(--panel);
  box-shadow: var(--shadow-menu);
}

.mobile-navigation-heading {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
}

.mobile-navigation-title {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.mobile-navigation-close {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: var(--control-touch-size);
  min-height: var(--control-touch-size);
  flex-shrink: 0;
  padding: var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--text-primary);
  cursor: pointer;
}

.mobile-navigation-close:hover {
  background: var(--surface-1);
}
</style>
