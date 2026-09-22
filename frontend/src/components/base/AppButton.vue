<script setup lang="ts">
// Three variants only (docs/25-frontend-design-guidelines.md): solid is the one primary action per
// view, ghost is secondary, text is tertiary/inline. Destructive actions use --critical; the
// guideline also asks for a confirmation step, which belongs to the call site once a destructive
// action actually exists (none does yet) rather than to this component.
withDefaults(
  defineProps<{
    variant?: 'solid' | 'ghost' | 'text'
    tone?: 'default' | 'destructive'
    type?: 'button' | 'submit' | 'reset'
    disabled?: boolean
  }>(),
  {
    variant: 'solid',
    tone: 'default',
    type: 'button',
    disabled: false,
  },
)
</script>

<template>
  <button
    :type="type"
    :disabled="disabled"
    class="app-button"
    :class="[`app-button--${variant}`, tone === 'destructive' && 'app-button--destructive']"
  >
    <slot />
  </button>
</template>

<style scoped>
.app-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border-radius: var(--radius-control);
  font: inherit;
  font-weight: var(--weight-semibold);
  padding: var(--space-2) var(--space-4);
  cursor: pointer;
}

.app-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.app-button--solid {
  border: 1px solid var(--accent-b);
  background: var(--accent-b);
  color: var(--panel);
}

.app-button--solid.app-button--destructive {
  border-color: var(--critical);
  background: var(--critical);
}

.app-button--ghost {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-primary);
}

.app-button--ghost.app-button--destructive {
  border-color: var(--critical);
  color: var(--critical);
}

.app-button--text {
  border: none;
  background: none;
  color: var(--accent);
  padding: var(--space-1) var(--space-2);
  text-underline-offset: 0.2em;
}

.app-button--text:hover:not(:disabled) {
  text-decoration: underline;
}

.app-button--text.app-button--destructive {
  color: var(--critical);
}
</style>
