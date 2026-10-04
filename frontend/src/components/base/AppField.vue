<script setup lang="ts">
import { computed } from 'vue'
import AppFieldHelp from './AppFieldHelp.vue'

const props = defineProps<{
  id: string
  label: string
  helpText?: string | undefined
  hideLabel?: boolean
  helpLabel?: string | undefined
  helpId?: string | undefined
  errorMessage?: string | undefined
  errorId?: string | undefined
  describedBy?: string | undefined
}>()
const helpDescriptionId = computed(() => props.helpId ?? `${props.id}-help`)
const errorDescriptionId = computed(() => props.errorId ?? `${props.id}-error`)
const descriptionIds = computed(() => {
  const ids = [
    props.describedBy,
    props.helpText ? helpDescriptionId.value : undefined,
    props.errorMessage ? errorDescriptionId.value : undefined,
  ]
    .filter(Boolean)
    .join(' ')
    .split(/\s+/)
    .filter(Boolean)
  return ids.length ? [...new Set(ids)].join(' ') : undefined
})
</script>

<template>
  <div class="app-field" :class="{ 'app-field--hidden-label': hideLabel }">
    <div v-if="helpText" class="app-field-label">
      <label :for="id">{{ label }}</label>
      <AppFieldHelp
        :description-id="helpDescriptionId"
        :label="helpLabel ?? label"
        :text="helpText"
      />
    </div>
    <label v-else :for="id">{{ label }}</label>
    <slot name="before-control" />
    <slot :description-ids="descriptionIds" />
    <slot name="description" />
    <p v-if="errorMessage" :id="errorDescriptionId" role="alert" class="app-field-error">
      {{ errorMessage }}
    </p>
  </div>
</template>

<style scoped>
.app-field {
  display: flex;
  min-width: 0;
  overflow-wrap: anywhere;
  flex-direction: column;
  gap: var(--field-gap, var(--space-1));
}
.app-field-label {
  display: flex;
  min-inline-size: 0;
  align-items: center;
  gap: var(--space-1);
}
label {
  min-block-size: var(--field-label-min-size, auto);
  align-content: center;
  font-size: var(--field-label-size, var(--font-size-small));
  font-weight: var(--field-label-weight, inherit);
  color: var(--field-label-color, var(--text-secondary));
}
.app-field-error {
  margin: 0;
  color: var(--critical-text);
  font-size: var(--field-error-size, var(--font-size-small));
}
.app-field--hidden-label > label {
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
</style>
