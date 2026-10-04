<script setup lang="ts">
import { useAttrs } from 'vue'
import type { HTMLAttributes, InputHTMLAttributes } from 'vue'
import AppField from './AppField.vue'

defineOptions({ inheritAttrs: false })
// Vue exposes fallthrough attributes as unknown; class/style retain their native Vue HTML types.
const attrs = useAttrs() as HTMLAttributes & Record<string, unknown>
// Layout belongs to the field; all other fallthrough attributes and native listeners target input.

// Every control has a visible label, and a validation message sits next to its field
// (docs/25-frontend-design-guidelines.md). `errorMessage` is opt-in: a form whose backend errors are
// not tied to one field (wrong username *or* password, deliberately not distinguished) keeps its
// error at the form level instead of inventing a field to blame.
const props = withDefaults(
  defineProps<{
    id: string
    label: string
    /** Defaults to `id`. Kept separate so the DOM id can stay page-unique while the field name
     * matches the API's request body key (`current_password`, not `change-password-current`). */
    name?: string
    type?: 'text' | 'password' | 'email' | 'search' | 'url' | 'tel' | 'number'
    autocomplete?: string
    required?: boolean
    minlength?: number
    maxlength?: number
    readonly?: boolean
    disabled?: boolean
    inputmode?: InputHTMLAttributes['inputmode']
    pattern?: string
    spellcheck?: InputHTMLAttributes['spellcheck']
    placeholder?: string
    min?: string | number
    max?: string | number
    helpText?: string | undefined
    helpLabel?: string | undefined
    helpId?: string | undefined
    errorId?: string | undefined
    errorMessage?: string | undefined
    ariaDescribedby?: string | undefined
    ariaInvalid?: InputHTMLAttributes['aria-invalid']
  }>(),
  {
    type: 'text',
    required: false,
  },
)

const model = defineModel<string>({ required: true })
</script>

<template>
  <AppField
    :id="id"
    class="app-text-field"
    v-bind="{ class: attrs.class, style: attrs.style }"
    :label="label"
    :help-text="helpText"
    :help-label="helpLabel"
    :help-id="helpId"
    :error-message="errorMessage"
    :error-id="errorId"
    :described-by="props.ariaDescribedby"
  >
    <template #before-control><slot name="before-control" /></template>
    <template #default="{ descriptionIds }">
      <input
        v-bind="{ ...attrs, class: undefined, style: undefined }"
        :id="id"
        v-model="model"
        :name="name ?? id"
        :type="type"
        :autocomplete="autocomplete"
        :required="required"
        :minlength="minlength"
        :maxlength="maxlength"
        :readonly="readonly"
        :disabled="disabled"
        :inputmode="inputmode"
        :pattern="pattern"
        :spellcheck="spellcheck"
        :placeholder="placeholder"
        :min="min"
        :max="max"
        :aria-invalid="errorMessage ? true : props.ariaInvalid"
        :aria-describedby="descriptionIds"
      />
    </template>
    <template #description><slot name="description" /></template>
  </AppField>
</template>

<style scoped>
.app-text-field input {
  min-width: 0;
  min-height: var(--control-min-size);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--field-control-background, var(--panel));
  color: var(--text-primary);
  font: var(--field-control-font, inherit);
  padding: var(--space-2) var(--space-3);
  width: var(--field-control-width, auto);
  max-width: var(--field-control-max-width, 100%);
}

.app-text-field input[aria-invalid='true'] {
  border-color: var(--critical);
}
</style>
