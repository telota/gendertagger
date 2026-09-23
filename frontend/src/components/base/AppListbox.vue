<script setup lang="ts" generic="T extends string">
// Behaviour and focus management come from the D9 library (docs/25-frontend-design-guidelines.md);
// appearance is ours. `ListboxLabel` gives the control a real accessible name without needing a
// separately laid-out <label> next to it, which suits a compact chrome control like this one.
import {
  Listbox,
  ListboxButton,
  ListboxLabel,
  ListboxOption,
  ListboxOptions,
} from '@headlessui/vue'
import { computed } from 'vue'

const props = defineProps<{
  label: string
  options: readonly { value: T; label: string }[]
}>()

const model = defineModel<T>({ required: true })

const currentLabel = computed(
  () => props.options.find((option) => option.value === model.value)?.label ?? '',
)
</script>

<template>
  <Listbox v-model="model" as="div" class="app-listbox">
    <ListboxLabel class="app-listbox-label">{{ label }}</ListboxLabel>
    <ListboxButton class="app-listbox-button">{{ currentLabel }}</ListboxButton>
    <ListboxOptions class="app-listbox-options">
      <ListboxOption
        v-for="option in options"
        :key="option.value"
        v-slot="{ active, selected }"
        :value="option.value"
        as="template"
      >
        <li
          class="app-listbox-option"
          :class="{
            'app-listbox-option--active': active,
            'app-listbox-option--selected': selected,
          }"
        >
          {{ option.label }}
        </li>
      </ListboxOption>
    </ListboxOptions>
  </Listbox>
</template>

<style scoped>
.app-listbox {
  position: relative;
}

.app-listbox-label {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.app-listbox-button {
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  font-size: var(--font-size-small);
  padding: var(--space-1) var(--space-3);
  cursor: pointer;
}

.app-listbox-options {
  position: absolute;
  z-index: 10;
  margin: var(--space-1) 0 0;
  padding: var(--space-1);
  min-width: 100%;
  list-style: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
}

.app-listbox-option {
  border-radius: var(--radius-control);
  padding: var(--space-1) var(--space-2);
  font-size: var(--font-size-small);
  white-space: nowrap;
  cursor: pointer;
}

.app-listbox-option--active {
  background: var(--surface-1);
}

.app-listbox-option--selected {
  font-weight: var(--weight-semibold);
  color: var(--accent);
}
</style>
