<script setup lang="ts" generic="T extends string | number | boolean | null">
import { useAttrs } from 'vue'
import type { HTMLAttributes, SelectHTMLAttributes } from 'vue'
import AppField from './AppField.vue'

defineOptions({ inheritAttrs: false })
// Vue exposes fallthrough attributes as unknown; class/style retain their native Vue HTML types.
const attrs = useAttrs() as HTMLAttributes & Record<string, unknown>
const props = defineProps<{
  id: string
  label: string
  hideLabel?: boolean
  name?: string
  disabled?: boolean
  required?: boolean
  autocomplete?: string
  helpText?: string | undefined
  helpLabel?: string | undefined
  helpId?: string | undefined
  errorMessage?: string | undefined
  errorId?: string | undefined
  ariaDescribedby?: string | undefined
  ariaInvalid?: SelectHTMLAttributes['aria-invalid']
}>()
const model = defineModel<T>({ required: true })
</script>

<template>
  <AppField
    :id="id"
    class="app-select-field"
    v-bind="{ class: attrs.class, style: attrs.style }"
    :label="label"
    :hide-label="hideLabel"
    :help-text="helpText"
    :help-label="helpLabel"
    :help-id="helpId"
    :error-message="errorMessage"
    :error-id="errorId"
    :described-by="props.ariaDescribedby"
  >
    <template #before-control><slot name="before-control" /></template>
    <template #default="{ descriptionIds }">
      <select
        v-bind="{ ...attrs, class: undefined, style: undefined }"
        :id="id"
        v-model="model"
        :name="name ?? id"
        :disabled="disabled"
        :required="required"
        :autocomplete="autocomplete"
        :aria-invalid="errorMessage ? true : props.ariaInvalid"
        :aria-describedby="descriptionIds"
      >
        <slot />
      </select>
    </template>
    <template #description><slot name="description" /></template>
  </AppField>
</template>

<style scoped>
select {
  width: var(--field-control-width, auto);
  max-width: var(--field-control-max-width, 100%);
  font: var(--field-control-font, inherit);
}
select[aria-invalid='true'] {
  border-color: var(--critical);
}
select:disabled {
  cursor: var(--field-disabled-cursor, not-allowed);
  opacity: var(--field-disabled-opacity, 1);
}
</style>
