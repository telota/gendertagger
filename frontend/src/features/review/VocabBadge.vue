<script setup lang="ts">
// One rendering for every controlled-vocabulary value: the untranslated token first, an optional
// plain-language gloss after it (D3). A missing value is rendered as an explicit dash with a text
// alternative, never as an empty cell, so "no label" cannot be mistaken for "not loaded".
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  /** The vocabulary token, or null/undefined when there is none. */
  value: string | null | undefined
  /** Plain-language gloss shown beside the token; empty for none. */
  gloss?: string
  /** Drives the colour: a canonical label uses its own token, everything else is neutral. */
  kind?: 'label' | 'tier' | 'state'
  /** Tier tone for certainty badges (`contested`, `low`, `thin`). */
  tone?: 'contested' | 'low' | 'thin' | 'neutral'
}>()

const { t } = useI18n()
const DASH = '\u2014'

const labelClass = computed(() =>
  props.kind === 'label' && props.value
    ? `vocab--${props.value}`
    : `vocab--${props.tone ?? 'neutral'}`,
)
</script>

<template>
  <span class="vocab" :class="labelClass">
    <template v-if="value">
      <span class="vocab-token">{{ value }}</span>
      <span v-if="gloss" class="vocab-gloss">{{ gloss }}</span>
    </template>
    <template v-else>
      <span aria-hidden="true">{{ DASH }}</span>
      <span class="vocab-none">{{ t('review.none') }}</span>
    </template>
  </span>
</template>

<style scoped>
.vocab {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 var(--space-2);
  padding: 0 var(--space-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: var(--font-size-small);
  white-space: nowrap;
}

.vocab-token {
  font-family: var(--font-mono, ui-monospace, monospace);
}

.vocab-gloss {
  color: var(--text-secondary);
}

/* The "none" wording is for assistive technology; the dash is what sighted users see. */
.vocab-none {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.vocab--male {
  background: var(--male-tint);
  border-color: var(--male);
  color: var(--male-text);
}

.vocab--female {
  background: var(--female-tint);
  border-color: var(--female);
  color: var(--female-text);
}

.vocab--institution {
  background: var(--institution-tint);
  border-color: var(--institution);
  color: var(--institution-text);
}

.vocab--unknown {
  background: var(--unknown-tint);
  border-color: var(--unknown);
  color: var(--unknown-text);
}

.vocab--contested {
  background: var(--female-tint);
  border-color: var(--female);
  color: var(--female-text);
}

.vocab--low {
  background: var(--unknown-tint);
  border-color: var(--unknown);
  color: var(--unknown-text);
}

.vocab--thin {
  background: var(--male-tint);
  border-color: var(--male);
  color: var(--male-text);
}
</style>
