<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { components } from '@/api/schema'
import VocabBadge from '@/components/domain/VocabBadge.vue'

withDefaults(
  defineProps<{ history: components['schemas']['AnnotationHistory']; review?: boolean }>(),
  { review: false },
)
const { t, d, n } = useI18n()
</script>

<template>
  <p v-if="!history.annotations.length" class="history-note">
    {{ t('review.detail.history.empty') }}
  </p>
  <template v-else>
    <p class="history-note">
      {{ t('review.detail.history.revision', { revision: n(history.revision, 'integer') }) }}
    </p>
    <ol class="history">
      <li
        v-for="(entry, index) in history.annotations"
        :key="entry.id"
        :class="{ 'history-entry--current': index === 0 }"
      >
        <p class="history-head">
          <span class="history-revision">{{
            t('review.detail.history.entry', { revision: n(entry.resulting_revision, 'integer') })
          }}</span>
          <span class="history-token">{{ entry.action }}</span>
          <VocabBadge v-if="entry.label" :value="entry.label" kind="label" />
          <span v-if="index === 0" class="history-current">{{
            t('review.detail.history.current')
          }}</span>
        </p>
        <p class="history-who">
          <span>{{
            t('review.detail.history.by', {
              name: entry.reviewer_display_name,
              when: d(new Date(entry.created_at), 'timestamp'),
            })
          }}</span>
          <span v-if="entry.supersedes_annotation_id" :class="{ 'history-replaces': review }">{{
            t('review.detail.history.replaces', {
              revision: n(entry.resulting_revision - 1, 'integer'),
            })
          }}</span>
        </p>
        <p v-if="entry.comment" class="history-comment">{{ entry.comment }}</p>
      </li>
    </ol>
  </template>
</template>

<style scoped>
.history-note {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
.history {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0 0 0 var(--space-4);
  border-inline-start: 2px solid var(--grid);
  list-style: none;
}
.history-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-2);
  margin: 0;
}
.history-entry--current .history-token,
.history-current {
  color: var(--accent);
}
.history-revision,
.history-current {
  font-size: var(--font-size-small);
}
.history-revision,
.history-who {
  color: var(--text-secondary);
}
.history-token {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: var(--weight-semibold);
}
.history-who {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  font-size: var(--font-size-small);
}
.history-replaces {
  margin-left: var(--space-2);
}
.history-comment {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
}
</style>
