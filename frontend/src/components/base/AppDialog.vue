<script setup lang="ts">
import { Dialog, DialogDescription, DialogPanel, DialogTitle } from '@headlessui/vue'

// Callers own dismissal policy, requests, and form submission. Headless UI owns focus and ARIA.
withDefaults(
  defineProps<{
    open: boolean
    size: 'sm' | 'md' | 'lg' | 'xl' | '2xl'
    scroll?: 'frame' | 'panel'
    layout?: 'flow' | 'stacked'
    backdrop?: 'theme' | 'ink'
    bordered?: boolean
    frameInset?: 'fixed' | 'inline-gutter' | 'gutter'
    panelInset?: 'fixed' | 'inline-gutter'
    titleSize?: 'page' | 'title'
    titleClass?: string
    descriptionClass?: string
    actionsClass?: string
    actionsAlign?: 'end' | 'start' | 'spread'
  }>(),
  {
    scroll: 'frame',
    layout: 'flow',
    backdrop: 'theme',
    frameInset: 'fixed',
    panelInset: 'fixed',
    bordered: false,
    titleSize: 'page',
    actionsAlign: 'end',
  },
)

const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <Dialog :open="open" class="app-dialog" @close="emit('close')">
    <div
      class="app-dialog-backdrop"
      :class="`app-dialog-backdrop--${backdrop}`"
      aria-hidden="true"
    />
    <div class="app-dialog-frame" :class="`app-dialog-frame--${frameInset}`">
      <DialogPanel
        class="app-dialog-panel"
        :class="[
          `app-dialog-panel--${size}`,
          `app-dialog-panel--${layout}`,
          `app-dialog-panel--${scroll}`,
          `app-dialog-panel--${panelInset}`,
          bordered && 'app-dialog-panel--bordered',
        ]"
      >
        <DialogTitle
          class="app-dialog-title"
          :class="[`app-dialog-title--${titleSize}`, titleClass]"
        >
          <slot name="title" />
        </DialogTitle>
        <DialogDescription
          v-if="$slots.description"
          class="app-dialog-description"
          :class="descriptionClass"
        >
          <slot name="description" />
        </DialogDescription>
        <slot />
        <div
          v-if="$slots.actions"
          class="app-dialog-actions"
          :class="[`app-dialog-actions--${actionsAlign}`, actionsClass]"
        >
          <slot name="actions" />
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>

<style>
/* Headless UI's portal root does not receive the component's scoped attribute. */
.app-dialog {
  position: relative;
}
</style>

<style scoped>
.app-dialog-backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
}

.app-dialog-backdrop--ink {
  background: color-mix(in srgb, var(--text-primary) 45%, transparent);
}

.app-dialog-frame {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: safe center;
  justify-content: center;
  overflow-y: auto;
  padding: var(--space-4);
}

.app-dialog-frame--inline-gutter {
  padding-inline: var(--page-gutter);
}

.app-dialog-frame--gutter {
  padding: var(--page-gutter);
}

.app-dialog-panel {
  flex-shrink: 0;
  min-width: 0;
  width: 100%;
  overflow-wrap: anywhere;
  padding: var(--space-6);
  border-radius: var(--radius-modal);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
}

.app-dialog-panel--sm {
  max-width: 24rem;
}
.app-dialog-panel--md {
  max-width: 28rem;
}
.app-dialog-panel--lg {
  max-width: 30rem;
}
.app-dialog-panel--xl {
  max-width: 32rem;
}
.app-dialog-panel--2xl {
  max-width: 34rem;
}

.app-dialog-panel--panel {
  max-height: calc(100dvh - 2 * var(--page-gutter));
  overflow-y: auto;
}

.app-dialog-panel--inline-gutter {
  padding-inline: var(--page-gutter);
}

.app-dialog-panel--bordered {
  border: 1px solid var(--border);
}

.app-dialog-panel--stacked {
  display: grid;
  gap: var(--space-4);
}

.app-dialog-title {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
}

.app-dialog-title--title {
  margin: 0;
  font-size: var(--font-size-title);
}

.app-dialog-description {
  margin: 0 0 var(--space-4);
  color: var(--text-secondary);
}

.app-dialog-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--space-3);
}

.app-dialog-actions--start {
  justify-content: flex-start;
}
.app-dialog-actions--spread {
  align-items: center;
  justify-content: space-between;
}
</style>
