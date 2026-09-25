<script setup lang="ts">
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
    type?: 'text' | 'password' | 'email'
    autocomplete?: string
    required?: boolean
    minlength?: number
    maxlength?: number
    readonly?: boolean
    errorMessage?: string | undefined
  }>(),
  {
    type: 'text',
    required: false,
  },
)

const model = defineModel<string>({ required: true })

const errorId = `${props.id}-error`
</script>

<template>
  <div class="app-text-field">
    <label :for="id">{{ label }}</label>
    <input
      :id="id"
      v-model="model"
      :name="name ?? id"
      :type="type"
      :autocomplete="autocomplete"
      :required="required"
      :minlength="minlength"
      :maxlength="maxlength"
      :readonly="readonly"
      :aria-invalid="errorMessage ? true : undefined"
      :aria-describedby="errorMessage ? errorId : undefined"
    />
    <p v-if="errorMessage" :id="errorId" role="alert" class="app-text-field-error">
      {{ errorMessage }}
    </p>
  </div>
</template>

<style scoped>
.app-text-field {
  display: flex;
  min-width: 0;
  overflow-wrap: anywhere;
  flex-direction: column;
  gap: var(--space-1);
}

.app-text-field label {
  font-size: var(--font-size-small);
  color: var(--text-secondary);
}

.app-text-field input {
  min-width: 0;
  min-height: var(--control-min-size);
  max-width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  padding: var(--space-2) var(--space-3);
}

.app-text-field input[aria-invalid='true'] {
  border-color: var(--critical);
}

.app-text-field-error {
  margin: 0;
  color: var(--critical-text);
  font-size: var(--font-size-small);
}
</style>
