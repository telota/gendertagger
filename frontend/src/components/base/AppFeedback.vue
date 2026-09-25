<script setup lang="ts">
// Presentation only: callers keep domain outcomes, recovery actions, and focus ownership.
// Keep dynamic feedback mounted when its text changes so the same live region can announce it.
// Actions stay outside that region; changing a retry button must not repeat the whole message.
withDefaults(
  defineProps<{
    announcement?: 'off' | 'polite' | 'assertive'
    tone?: 'default' | 'critical'
  }>(),
  { announcement: 'off', tone: 'default' },
)
</script>

<template>
  <div class="app-feedback" :class="`app-feedback--${tone}`">
    <div
      class="app-feedback-message"
      :role="
        announcement === 'polite' ? 'status' : announcement === 'assertive' ? 'alert' : undefined
      "
      :aria-atomic="announcement === 'off' ? undefined : true"
    >
      <slot />
    </div>
    <div v-if="$slots.actions" class="app-feedback-actions"><slot name="actions" /></div>
  </div>
</template>

<style scoped>
.app-feedback {
  display: grid;
  gap: var(--space-3);
  min-inline-size: 0;
  max-inline-size: 100%;
  overflow-wrap: anywhere;
}

.app-feedback-message {
  min-inline-size: 0;
}

.app-feedback-message > :slotted(p) {
  margin: 0;
}

.app-feedback-message > :slotted(p + p) {
  margin-block-start: var(--space-2);
}

.app-feedback--critical > .app-feedback-message {
  color: var(--critical-text);
}

.app-feedback-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  min-inline-size: 0;
}
</style>
