<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import { useSnapshotStatus } from '@/features/projects/useSnapshotImport'
import { useAggregationList } from '@/features/runs/useAggregations'
import { useRun } from '@/features/runs/useRunDetail'

import { useCreateExport, type ExportFormat, type LabelSourcePolicy } from './useExports'

const props = defineProps<{ projectId: string; runId: string }>()

const { t } = useI18n()
const router = useRouter()

const runId = computed(() => props.runId)
const aggregations = useAggregationList(runId)
const run = useRun(runId)
const create = useCreateExport()

// An export is over one completed aggregation (its labels are what is exported).
const completed = computed(() =>
  (aggregations.data.value?.pages.flatMap((page) => page.items) ?? []).filter(
    (aggregation) => aggregation.status === 'completed',
  ),
)
const pickedAggregation = ref<string | null>(null)
const aggregationId = computed({
  get: () => pickedAggregation.value ?? completed.value[0]?.id ?? '',
  set: (value: string) => {
    pickedAggregation.value = value
  },
})

const format = ref<ExportFormat>('tei')
// What an export shows for each person: the machine's decision, or the human decision where there is one.
// The vocabulary values are shown as they are (D3), never translated.
const POLICY_MACHINE: LabelSourcePolicy = 'machine_aggregation'
const POLICY_HUMAN: LabelSourcePolicy = 'human_overrides'
const policy = ref<LabelSourcePolicy>(POLICY_MACHINE)
const TEI_PROFILE = 'tei_p5_gender_v1'
// The TEI @resp value naming the human editor; the server requires "#" and no whitespace.
const DEFAULT_RESP = '#editor'
const respId = ref(DEFAULT_RESP)
const respValid = computed(() => /^#\S+$/.test(respId.value) && respId.value.length <= 200)

// A TEI export writes the labels back into the source files, so it needs a TEI snapshot that is
// still those files (a single file or loose files). The snapshot says which it is.
const snapshotId = computed(() => run.data.value?.dataset_snapshot_id ?? null)
const snapshot = useSnapshotStatus(snapshotId)
const teiPossible = computed(() => {
  const config = snapshot.data.value?.import_config
  if (!config) return true // not known yet: the server decides
  const sourceFormat = config['source_format']
  const packaging = config['packaging']
  return sourceFormat === 'tei' && (packaging === 'single' || packaging === 'loose')
})

const canSubmit = computed(
  () =>
    aggregationId.value !== '' &&
    !create.isPending.value &&
    (format.value !== 'tei' || (teiPossible.value && respValid.value)),
)

const errorText = computed(() => {
  const error = create.error.value
  if (!create.isError.value || error === null) return ''
  if (error instanceof ApiError && error.code === 'resource_conflict') {
    return t('export.new.errors.conflict')
  }
  if (error instanceof ApiError && error.code === 'network_error') {
    return t('export.new.errors.network')
  }
  return t('export.new.errors.generic')
})

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  try {
    const created = await create.mutateAsync({
      run_id: props.runId,
      aggregation_execution_id: aggregationId.value,
      format: format.value,
      label_source_policy: policy.value,
      // Only TEI has a profile, and the server refuses one otherwise. The responsibility statement is
      // required by the contract; outside TEI it is not used, so the default is sent.
      human_resp_id: format.value === 'tei' ? respId.value : DEFAULT_RESP,
      ...(format.value === 'tei' ? { tei_profile: TEI_PROFILE } : {}),
    })
    void router.push({
      name: 'exportDetail',
      params: { projectId: props.projectId, runId: props.runId, exportId: created.id },
    })
  } catch {
    // create.isError/.error already reflect this; the form stays filled to be corrected.
  }
}
</script>

<template>
  <form class="new-export" novalidate aria-labelledby="new-export-heading" @submit.prevent="submit">
    <h2 id="new-export-heading" class="new-export-title">{{ t('export.new.title') }}</h2>

    <p v-if="aggregations.isPending.value" role="status">{{ t('runs.loading') }}</p>
    <p v-else-if="completed.length === 0" class="new-export-hint">
      {{ t('export.new.noAggregation') }}
    </p>
    <template v-else>
      <div class="new-export-field">
        <label for="export-aggregation">{{ t('export.new.aggregation') }}</label>
        <select id="export-aggregation" v-model="aggregationId">
          <option v-for="aggregation in completed" :key="aggregation.id" :value="aggregation.id">
            {{
              t('export.new.aggregationOption', {
                strategy: aggregation.strategy ?? '',
                hash: aggregation.config_sha256.slice(0, 8),
              })
            }}
          </option>
        </select>
      </div>

      <fieldset class="new-export-field">
        <legend>{{ t('export.new.format') }}</legend>
        <div class="new-export-choice">
          <input id="export-format-tei" v-model="format" type="radio" name="format" value="tei" />
          <label for="export-format-tei">{{ t('export.new.formats.tei') }}</label>
        </div>
        <div class="new-export-choice">
          <input id="export-format-json" v-model="format" type="radio" name="format" value="json" />
          <label for="export-format-json">{{ t('export.new.formats.json') }}</label>
        </div>
        <div class="new-export-choice">
          <input id="export-format-csv" v-model="format" type="radio" name="format" value="csv" />
          <label for="export-format-csv">{{ t('export.new.formats.csv') }}</label>
        </div>
        <p v-if="format === 'tei' && !teiPossible" role="alert" class="new-export-error">
          {{ t('export.new.teiNotPossible') }}
        </p>
      </fieldset>

      <fieldset class="new-export-field">
        <legend>{{ t('export.new.policy') }}</legend>
        <div class="new-export-choice">
          <input
            id="export-policy-machine"
            v-model="policy"
            type="radio"
            name="policy"
            value="machine_aggregation"
          />
          <label for="export-policy-machine">
            <span class="new-export-token">{{ POLICY_MACHINE }}</span>
            {{ t('export.new.policies.machine') }}
          </label>
        </div>
        <div class="new-export-choice">
          <input
            id="export-policy-human"
            v-model="policy"
            type="radio"
            name="policy"
            value="human_overrides"
          />
          <label for="export-policy-human">
            <span class="new-export-token">{{ POLICY_HUMAN }}</span>
            {{ t('export.new.policies.human') }}
          </label>
        </div>
        <p class="new-export-hint">{{ t('export.new.policyHint') }}</p>
      </fieldset>

      <template v-if="format === 'tei'">
        <div class="new-export-field">
          <span class="new-export-label">{{ t('export.new.profile') }}</span>
          <span class="new-export-token">{{ TEI_PROFILE }}</span>
        </div>
        <div class="new-export-field">
          <label for="export-resp">{{ t('export.new.resp') }}</label>
          <input
            id="export-resp"
            v-model="respId"
            type="text"
            autocomplete="off"
            :aria-invalid="!respValid"
            aria-describedby="export-resp-hint"
          />
          <p id="export-resp-hint" class="new-export-hint">{{ t('export.new.respHint') }}</p>
          <p v-if="!respValid" role="alert" class="new-export-error">
            {{ t('export.new.respInvalid') }}
          </p>
        </div>
      </template>

      <p v-if="errorText" role="alert" class="new-export-error">{{ errorText }}</p>
      <AppButton class="new-export-submit" type="submit" :disabled="!canSubmit">
        {{ create.isPending.value ? t('export.new.submitting') : t('export.new.submit') }}
      </AppButton>
    </template>
  </form>
</template>

<style scoped>
.new-export {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.new-export-title {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.new-export-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  border: 0;
  font-size: var(--font-size-small);
}

.new-export-field legend {
  padding: 0;
  font-weight: var(--weight-semibold);
}

.new-export-choice {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-1);
}

.new-export-hint {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.new-export-token {
  font-family: var(--font-mono, ui-monospace, monospace);
}

.new-export-error {
  margin: 0;
  color: var(--critical);
}
</style>
