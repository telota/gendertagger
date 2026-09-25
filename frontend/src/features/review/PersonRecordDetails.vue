<script setup lang="ts">
// The register entry as the source stored it. Everything here is source-preserving (docs/23): name
// forms with their type and subtype, dated events, authority identifiers, and where in which source
// file the record came from, so a reviewer can go back to the original when a decision hinges on it.
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { PersonRecord } from './useReviewData'

const props = defineProps<{ record: PersonRecord }>()

const { t } = useI18n()

const facts = computed(() => {
  const record = props.record
  const rows: { key: string; label: string; value: string }[] = []
  if (record.birth)
    rows.push({ key: 'birth', label: t('review.detail.person.birth'), value: record.birth })
  if (record.death)
    rows.push({ key: 'death', label: t('review.detail.person.death'), value: record.death })
  if (record.gnd_id)
    rows.push({ key: 'gnd', label: t('review.detail.person.gnd'), value: record.gnd_id })
  if (record.alt_names && record.alt_names.length > 0) {
    rows.push({
      key: 'altNames',
      label: t('review.detail.person.altNames'),
      value: record.alt_names.join('; '),
    })
  }
  if (record.note)
    rows.push({ key: 'note', label: t('review.detail.person.note'), value: record.note })
  return rows
})

function formName(form: NonNullable<PersonRecord['name_forms']>[number]): string {
  const forenames = (form.forenames ?? []).join(' ')
  if (form.name) return form.name
  if (form.surname && forenames) return `${form.surname}, ${forenames}`
  return form.surname ?? forenames
}

/** A key from the content (never the array position); an exact repeat gets a counter. */
function keyed<T>(items: readonly T[], base: (item: T) => string): { item: T; key: string }[] {
  const seen = new Map<string, number>()
  return items.map((item) => {
    const key = base(item)
    const count = (seen.get(key) ?? 0) + 1
    seen.set(key, count)
    return { item, key: count === 1 ? key : `${key}#${count}` }
  })
}

const nameForms = computed(() =>
  keyed(
    props.record.name_forms ?? [],
    (form) => `${form.type}|${form.subtype ?? ''}|${formName(form)}`,
  ),
)
const events = computed(() =>
  keyed(
    props.record.events ?? [],
    (event) => `${event.type}|${event.when ?? ''}|${event.note ?? ''}`,
  ),
)
const externalIds = computed(() => Object.entries(props.record.external_ids ?? {}))

const hasSource = computed(
  () => !!props.record.source_member_name || !!props.record.source_record_locator,
)
const isEmpty = computed(
  () =>
    facts.value.length === 0 &&
    nameForms.value.length === 0 &&
    events.value.length === 0 &&
    externalIds.value.length === 0 &&
    !hasSource.value,
)
</script>

<template>
  <div class="record">
    <p v-if="isEmpty" class="record-muted">{{ t('review.detail.person.empty') }}</p>

    <dl v-if="facts.length > 0" class="record-facts app-facts">
      <div v-for="fact in facts" :key="fact.key" class="record-fact app-fact">
        <dt>{{ fact.label }}</dt>
        <dd>{{ fact.value }}</dd>
      </div>
    </dl>

    <div v-if="nameForms.length > 0" class="record-block">
      <p class="record-subtitle">{{ t('review.detail.person.nameForms') }}</p>
      <ul class="record-list">
        <li v-for="entry in nameForms" :key="entry.key" class="record-name-form">
          <span class="record-token">{{ entry.item.type }}</span>
          <span v-if="entry.item.subtype" class="record-token">{{ entry.item.subtype }}</span>
          <span>{{ formName(entry.item) }}</span>
        </li>
      </ul>
    </div>

    <div v-if="events.length > 0" class="record-block">
      <p class="record-subtitle">{{ t('review.detail.person.events') }}</p>
      <ul class="record-list">
        <li v-for="entry in events" :key="entry.key" class="record-event">
          <span class="record-token">{{ entry.item.type }}</span>
          <span v-if="entry.item.when">{{ entry.item.when }}</span>
          <span v-if="entry.item.note" class="record-muted">{{ entry.item.note }}</span>
        </li>
      </ul>
    </div>

    <div v-if="externalIds.length > 0" class="record-block">
      <p class="record-subtitle">{{ t('review.detail.person.externalIds') }}</p>
      <ul class="record-list">
        <li v-for="[scheme, value] in externalIds" :key="scheme" class="record-external-id">
          <span class="record-token">{{ scheme }}</span>
          <span>{{ value }}</span>
        </li>
      </ul>
    </div>

    <p v-if="hasSource" class="record-source">
      {{
        t('review.detail.person.source', {
          file: record.source_member_name ?? t('review.none'),
          locator: record.source_record_locator ?? t('review.none'),
        })
      }}
    </p>
  </div>
</template>

<style scoped>
.record {
  min-width: 0;
  overflow-wrap: anywhere;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.record-facts {
  display: grid;
  gap: var(--space-2);
  margin: 0;
}

.record-fact dt {
  color: var(--text-secondary);
}

.record-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.record-subtitle {
  margin: 0 0 var(--space-1);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.record-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.record-list li {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: baseline;
  overflow-wrap: anywhere;
}

.record-token {
  min-width: 0;
  max-width: 100%;
  padding: 0 var(--space-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: var(--font-size-small);
}

.record-muted,
.record-source {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
</style>
