<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'

import { useMethodList } from './useMethods'
import { useCreateRun, type MethodRunConfig, type Run } from './useRuns'

const props = defineProps<{ snapshotId: string }>()
const emit = defineEmits<{ created: [run: Run] }>()

const { t, n } = useI18n()

const methods = useMethodList()
const createRun = useCreateRun()

const selected = reactive<Record<string, boolean>>({})
// Per-method configuration as JSON text. The contract has no configuration schema (only the
// server-side registry knows it), so the form cannot offer typed fields; the server validates.
const configText = reactive<Record<string, string>>({})
const failOnOptionalError = ref(false)

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
  if (!canSubmit.value) return
  const methodConfigs: MethodRunConfig[] = chosen.value.map((method) => {
    const parsed = parseConfig(configText[method.name])
    return {
      name: method.name,
      enabled: true,
      // JsonValue in the contract; `parseConfig` only ever yields a plain JSON object here.
      config: (parsed.ok ? parsed.value : {}) as NonNullable<MethodRunConfig['config']>,
    }
  })
  try {
    const run = await createRun.mutateAsync({
      snapshotId: props.snapshotId,
      config: {
        methods: methodConfigs,
        execution: { fail_run_on_optional_method_error: failOnOptionalError.value },
      },
    })
    emit('created', run)
    for (const key of Object.keys(selected)) selected[key] = false
    for (const key of Object.keys(configText)) configText[key] = ''
  } catch {
    // createRun.isError/.error already reflect this; the form stays filled to be corrected.
  }
}
</script>

<template>
  <form class="new-run" novalidate aria-labelledby="new-run-heading" @submit.prevent="submit">
    <h2 id="new-run-heading" class="new-run-title">{{ t('runs.new.title') }}</h2>

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
        <ul class="new-run-method-list">
          <li v-for="method in methods.data.value" :key="method.name" class="new-run-method">
            <div class="new-run-method-head">
              <input
                :id="`method-${method.name}`"
                v-model="selected[method.name]"
                type="checkbox"
                :aria-describedby="`method-${method.name}-facts`"
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
            <div v-if="selected[method.name]" class="new-run-config">
              <label :for="`config-${method.name}`">{{ t('runs.new.config') }}</label>
              <textarea
                :id="`config-${method.name}`"
                v-model="configText[method.name]"
                class="new-run-config-input"
                rows="4"
                spellcheck="false"
                :aria-invalid="invalidConfigFor(method.name)"
                :aria-describedby="`config-${method.name}-hint`"
              />
              <p :id="`config-${method.name}-hint`" class="new-run-hint">
                {{ t('runs.new.configHint') }}
              </p>
              <p v-if="invalidConfigFor(method.name)" role="alert" class="new-run-error">
                {{ t('runs.new.errors.notJsonObject') }}
              </p>
            </div>
          </li>
        </ul>
      </fieldset>

      <div class="new-run-option">
        <input id="fail-on-optional" v-model="failOnOptionalError" type="checkbox" />
        <label for="fail-on-optional">{{ t('runs.new.failOnOptionalError') }}</label>
      </div>

      <p v-if="createRun.isError.value" role="alert" class="new-run-error">
        {{ errorMessage(createRun.error.value) }}
      </p>
      <AppButton
        class="new-run-submit"
        type="submit"
        :disabled="!canSubmit || createRun.isPending.value"
      >
        {{ createRun.isPending.value ? t('runs.new.submitting') : t('runs.new.submit') }}
      </AppButton>
    </template>
  </form>
</template>

<style scoped>
.new-run {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-4);
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
  color: var(--critical);
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

.new-run-method-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin: var(--space-3) 0 0;
  padding: 0;
  list-style: none;
}

.new-run-method {
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.new-run-method-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.new-run-method-name {
  font-weight: var(--weight-semibold);
}

.new-run-method-facts {
  margin: var(--space-1) 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.new-run-config {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

.new-run-config-input {
  width: 100%;
  font-family: var(--font-mono, monospace);
  font-size: var(--font-size-small);
}

.new-run-option {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
</style>
