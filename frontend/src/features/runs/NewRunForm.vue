<script setup lang="ts">
import { computed, onScopeDispose, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import { useDraftRegistration } from '@/composables/useDraftNavigation'

import { useMethodList } from '@/composables/useMethods'
import { useCreateRun } from '@/composables/useRuns'
import type { components } from '@/api/schema'

type MethodRunConfig = components['schemas']['MethodRunConfig']
type Run = components['schemas']['Run']

const props = defineProps<{ snapshotId: string }>()
const emit = defineEmits<{ created: [run: Run] }>()

const { t, n } = useI18n()
const heading = ref<HTMLElement>()
defineExpose({ focusHeading: () => heading.value?.focus() })

const methods = useMethodList()
const createRun = useCreateRun()

const selected = reactive<Record<string, boolean>>({})
// Per-method configuration as JSON text. The contract has no configuration schema (only the
// server-side registry knows it), so the form cannot offer typed fields; the server validates.
const configText = reactive<Record<string, string>>({})
const failOnOptionalError = ref(false)
const draftFingerprint = computed(() =>
  JSON.stringify([
    Object.keys(selected)
      .filter((name) => selected[name])
      .sort(),
    Object.entries(configText)
      .filter(([, text]) => text.trim() !== '')
      .sort(([a], [b]) => a.localeCompare(b)),
    failOnOptionalError.value,
  ]),
)
const savedDraft = ref(draftFingerprint.value)
let draftGeneration = 0

function resetDraft(): void {
  draftGeneration += 1
  createRun.reset()
  for (const key of Object.keys(selected)) selected[key] = false
  for (const key of Object.keys(configText)) configText[key] = ''
  failOnOptionalError.value = false
  savedDraft.value = draftFingerprint.value
}
useDraftRegistration(
  () => draftFingerprint.value !== savedDraft.value || createRun.isPending.value,
  resetDraft,
)
watch(() => props.snapshotId, resetDraft)
onScopeDispose(() => {
  draftGeneration += 1
})

type ConfigParse = { ok: true; value: Record<string, unknown> } | { ok: false }

function parseConfig(text: string | undefined): ConfigParse {
  const source = (text ?? '').trim()
  if (source === '') return { ok: true, value: {} }
  try {
    const parsed: unknown = JSON.parse(source)
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return { ok: true, value: parsed as Record<string, unknown> }
    }
  } catch {
    // fall through: not JSON at all
  }
  return { ok: false }
}

function selectAllAvailable(): void {
  for (const method of methods.data.value ?? []) {
    selected[method.name] = method.available
  }
}

const chosen = computed(() => (methods.data.value ?? []).filter((m) => selected[m.name]))
const invalidConfigFor = (name: string): boolean => !parseConfig(configText[name]).ok
const hasInvalidConfig = computed(() => chosen.value.some((m) => invalidConfigFor(m.name)))
const canSubmit = computed(() => chosen.value.length > 0 && !hasInvalidConfig.value)

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'validation_error':
        return t('runs.new.errors.invalidConfig')
      case 'network_error':
        return t('runs.new.errors.network')
    }
  }
  return t('runs.new.errors.generic')
}

async function submit(): Promise<void> {
  if (!canSubmit.value || createRun.isPending.value) return
  const methodConfigs: MethodRunConfig[] = chosen.value.map((method) => {
    const parsed = parseConfig(configText[method.name])
    return {
      name: method.name,
      enabled: true,
      // JsonValue in the contract; `parseConfig` only ever yields a plain JSON object here.
      config: (parsed.ok ? parsed.value : {}) as NonNullable<MethodRunConfig['config']>,
    }
  })
  const owner = draftGeneration
  const submittedDraft = draftFingerprint.value
  try {
    const run = await createRun.mutateAsync({
      snapshotId: props.snapshotId,
      config: {
        methods: methodConfigs,
        execution: { fail_run_on_optional_method_error: failOnOptionalError.value },
      },
    })
    if (owner !== draftGeneration) return
    if (draftFingerprint.value === submittedDraft) {
      for (const key of Object.keys(selected)) selected[key] = false
      for (const key of Object.keys(configText)) configText[key] = ''
      savedDraft.value = draftFingerprint.value
    } else {
      // Input added while this request was pending belongs to the next run.
      savedDraft.value = submittedDraft
    }
    emit('created', run)
  } catch {
    // createRun.isError/.error already reflect this; the form stays filled to be corrected.
  }
}
</script>

<template>
  <form class="new-run" novalidate aria-labelledby="new-run-heading" @submit.prevent="submit">
    <h2 id="new-run-heading" ref="heading" class="new-run-title" tabindex="-1">
      {{ t('runs.new.title') }}
    </h2>

    <p v-if="methods.isPending.value" role="status">{{ t('runs.loading') }}</p>
    <div v-else-if="methods.isError.value" class="new-run-load-error">
      <p role="alert">{{ t('runs.new.methodsLoadError') }}</p>
      <AppButton class="new-run-retry" type="button" @click="() => methods.refetch()">
        {{ t('runs.retry') }}
      </AppButton>
    </div>
    <template v-else>
      <fieldset class="new-run-methods">
        <legend>{{ t('runs.new.methods') }}</legend>
        <p class="new-run-hint">{{ t('runs.new.methodsHint') }}</p>
        <AppButton
          class="new-run-select-all"
          type="button"
          variant="ghost"
          @click="selectAllAvailable"
        >
          {{ t('runs.new.selectAll') }}
        </AppButton>
        <ul class="new-run-method-list">
          <li
            v-for="method in methods.data.value"
            :key="method.name"
            class="new-run-method"
            :class="{ 'new-run-method--unavailable': !method.available }"
          >
            <div class="new-run-method-head">
              <input
                :id="`method-${method.name}`"
                v-model="selected[method.name]"
                type="checkbox"
                :disabled="!method.available"
                :aria-describedby="
                  method.available
                    ? `method-${method.name}-facts`
                    : `method-${method.name}-facts method-${method.name}-unavailable`
                "
              />
              <label :for="`method-${method.name}`" class="new-run-method-name">{{
                method.name
              }}</label>
            </div>
            <p :id="`method-${method.name}-facts`" class="new-run-method-facts">
              {{
                method.method_confidence_range
                  ? t('runs.new.versionWithConfidence', {
                      version: method.implementation_version,
                      min: n(method.method_confidence_range.minimum, 'decimal'),
                      max: n(method.method_confidence_range.maximum, 'decimal'),
                    })
                  : t('runs.new.version', { version: method.implementation_version })
              }}
            </p>
            <p
              v-if="!method.available"
              :id="`method-${method.name}-unavailable`"
              class="new-run-method-unavailable"
            >
              {{ t('runs.new.needsConfiguration') }}
            </p>
            <details v-if="selected[method.name]" class="new-run-config">
              <summary>{{ t('runs.new.configureMethod') }}</summary>
              <div class="new-run-config-fields">
                <label :for="`config-${method.name}`">{{ t('runs.new.config') }}</label>
                <textarea
                  :id="`config-${method.name}`"
                  v-model="configText[method.name]"
                  class="new-run-config-input app-multiline-field"
                  rows="4"
                  spellcheck="false"
                  :aria-invalid="invalidConfigFor(method.name)"
                  :aria-describedby="`config-${method.name}-hint${invalidConfigFor(method.name) ? ` config-${method.name}-error` : ''}`"
                />
                <p :id="`config-${method.name}-hint`" class="new-run-hint">
                  {{ t('runs.new.configHint') }}
                </p>
                <p
                  v-if="invalidConfigFor(method.name)"
                  :id="`config-${method.name}-error`"
                  role="alert"
                  class="new-run-error"
                >
                  {{ t('runs.new.errors.notJsonObject') }}
                </p>
              </div>
            </details>
          </li>
        </ul>
      </fieldset>

      <details class="new-run-advanced">
        <summary>{{ t('runs.new.advanced') }}</summary>
        <div class="new-run-option">
          <input id="fail-on-optional" v-model="failOnOptionalError" type="checkbox" />
          <label for="fail-on-optional">{{ t('runs.new.failOnOptionalError') }}</label>
        </div>
      </details>

      <p v-if="createRun.isError.value" role="alert" class="new-run-error">
        {{ errorMessage(createRun.error.value) }}
      </p>
      <div class="app-form-actions">
        <AppButton
          class="new-run-submit"
          type="submit"
          :disabled="!canSubmit || createRun.isPending.value"
        >
          {{ createRun.isPending.value ? t('runs.new.submitting') : t('runs.new.submit') }}
        </AppButton>
      </div>
    </template>
  </form>
</template>

<style scoped>
.new-run {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
  min-inline-size: 0;
}

.new-run-title {
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.new-run-load-error {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-3);
}

.new-run-load-error p,
.new-run-error {
  margin: 0;
  color: var(--critical-text);
}

.new-run-methods {
  width: 100%;
  margin: 0;
  padding: 0;
  border: 0;
}

.new-run-methods legend {
  padding: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.new-run-hint {
  margin: var(--space-1) 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.new-run-select-all {
  margin-block-start: var(--space-2);
}

.new-run-method-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr));
  gap: var(--space-4);
  margin: var(--space-3) 0 0;
  padding: 0;
  list-style: none;
}

.new-run-method {
  min-inline-size: 0;
  padding-block: var(--space-3);
  border-block-start: 1px solid var(--border);
}

.new-run-method-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.new-run-method-name {
  font-weight: var(--weight-semibold);
  overflow-wrap: anywhere;
  padding-block: var(--space-2);
}

.new-run-method--unavailable .new-run-method-name {
  color: var(--text-secondary);
}

.new-run-method-facts {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.new-run-method-unavailable {
  margin: var(--space-1) 0 0;
  color: var(--critical-text);
  font-size: var(--font-size-small);
}

.new-run-config {
  margin-top: var(--space-3);
}
.new-run-config summary,
.new-run-advanced summary {
  cursor: pointer;
  font-weight: var(--weight-semibold);
  padding-block: var(--space-2);
}
.new-run-config-fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.new-run-config-input {
  font-family: var(--font-mono, monospace);
  font-size: var(--font-size-small);
}

.new-run-option {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-block-start: var(--space-2);
}
</style>
