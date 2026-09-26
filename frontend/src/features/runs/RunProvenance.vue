<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Run } from './useRuns'

const props = defineProps<{ run: Run }>()

const { t } = useI18n()

// What produced this run: the code, the environment and the exact configuration
// (docs/11-provenance-and-reproducibility.md). A value that was not recorded is said to be so,
// never left out, so an absent digest cannot be mistaken for one nobody looked at.
const rows = computed(() => [
  { key: 'codeCommit', label: t('runs.provenance.codeCommit'), value: props.run.code_git_commit },
  {
    key: 'applicationVersion',
    label: t('runs.provenance.applicationVersion'),
    value: props.run.application_version,
  },
  {
    key: 'pythonVersion',
    label: t('runs.provenance.pythonVersion'),
    value: props.run.python_version,
  },
  {
    key: 'imageDigest',
    label: t('runs.provenance.imageDigest'),
    value: props.run.container_image_digest ?? null,
  },
  {
    key: 'dependencyLockHash',
    label: t('runs.provenance.dependencyLockHash'),
    value: props.run.dependency_lock_sha256 ?? null,
  },
  {
    key: 'dependencyLockArtifact',
    label: t('runs.provenance.dependencyLockArtifact'),
    value: props.run.dependency_lock_artifact_id ?? null,
  },
  { key: 'configHash', label: t('runs.provenance.configHash'), value: props.run.config_sha256 },
])

const resolvedConfig = computed(() => JSON.stringify(props.run.resolved_config, null, 2))
</script>

<template>
  <details class="provenance">
    <summary class="provenance-summary">
      <h2 class="provenance-title">{{ t('runs.provenance.title') }}</h2>
    </summary>
    <div class="provenance-content">
      <p class="provenance-hint">{{ t('runs.provenance.hint') }}</p>
      <dl class="provenance-facts">
        <div v-for="row in rows" :key="row.key" class="provenance-fact" :data-key="row.key">
          <dt>{{ row.label }}</dt>
          <dd>
            <code v-if="row.value" class="provenance-value">{{ row.value }}</code>
            <span v-else class="provenance-missing">{{ t('runs.provenance.notRecorded') }}</span>
          </dd>
        </div>
      </dl>
      <details class="provenance-config">
        <summary>{{ t('runs.provenance.resolvedConfig') }}</summary>
        <pre class="provenance-config-json">{{ resolvedConfig }}</pre>
      </details>
    </div>
  </details>
</template>

<style scoped>
.provenance {
  width: 100%;
  border-block-start: 1px solid var(--border);
  padding-block: var(--space-3);
  container: provenance / inline-size;
}
.provenance-summary {
  cursor: pointer;
  padding-block: var(--space-2);
}
.provenance-content {
  margin-block-start: var(--space-3);
}

.provenance-title {
  display: inline;
  margin: 0;
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.provenance-hint {
  margin: 0 0 var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.provenance-facts {
  display: grid;
  gap: var(--space-2);
  margin: 0 0 var(--space-3);
}

.provenance-fact {
  display: grid;
  grid-template-columns: 12rem 1fr;
  gap: var(--space-3);
}

.provenance-fact dt {
  color: var(--text-secondary);
}

.provenance-fact dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.provenance-value {
  font-size: var(--font-size-small);
}

.provenance-missing {
  color: var(--text-secondary);
}

.provenance-config summary {
  cursor: pointer;
  font-weight: var(--weight-semibold);
}

.provenance-config-json {
  margin: var(--space-2) 0 0;
  padding: var(--space-3);
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
  font-size: var(--font-size-small);
}
@container provenance (max-width: 32rem) {
  .provenance-fact {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-1);
  }
}
</style>
