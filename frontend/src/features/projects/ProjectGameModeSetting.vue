<script setup lang="ts">
import { ref, toRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'

import ProjectOverviewSection from './ProjectOverviewSection.vue'
import { useSetProjectGameMode } from './useProjects'

const props = defineProps<{
  projectId: string
  enabled: boolean
}>()
const { t } = useI18n()
const update = useSetProjectGameMode(toRef(props, 'projectId'))
const requestedValue = ref(props.enabled)
const displayedEnabled = ref(props.enabled)
watch(
  () => props.enabled,
  (enabled) => {
    displayedEnabled.value = enabled
  },
)

async function save(enabled: boolean): Promise<void> {
  requestedValue.value = enabled
  displayedEnabled.value = enabled
  try {
    await update.mutateAsync(enabled)
  } catch {
    displayedEnabled.value = props.enabled
    // The mutation exposes the typed request failure in the inline feedback below.
  }
}

function onChange(event: Event): void {
  void save((event.target as HTMLInputElement).checked)
}
</script>

<template>
  <ProjectOverviewSection :title="t('projects.overview.gameMode.title')">
    <div class="game-mode-setting">
      <div class="game-mode-setting__copy">
        <p id="project-game-mode-hint">{{ t('projects.overview.gameMode.hint') }}</p>
        <p class="game-mode-setting__retention">
          {{ t('projects.overview.gameMode.retention') }}
        </p>
      </div>
      <label class="game-mode-setting__control">
        <input
          type="checkbox"
          :checked="displayedEnabled"
          :disabled="update.isPending.value"
          aria-describedby="project-game-mode-hint"
          @change="onChange"
        />
        <span>
          {{
            displayedEnabled
              ? t('projects.overview.gameMode.enabled')
              : t('projects.overview.gameMode.disabled')
          }}
        </span>
      </label>
    </div>

    <p
      v-if="update.isPending.value"
      id="project-game-mode-status"
      class="game-mode-setting__status"
      role="status"
    >
      {{ t('projects.overview.gameMode.saving') }}
    </p>
    <p
      v-else-if="update.isSuccess.value"
      id="project-game-mode-status"
      class="game-mode-setting__status"
      role="status"
    >
      {{ t('projects.overview.gameMode.saved') }}
    </p>
    <AppFeedback
      v-else-if="update.isError.value"
      id="project-game-mode-status"
      tone="critical"
      announcement="assertive"
    >
      <p>{{ t('projects.overview.gameMode.saveError') }}</p>
      <template #actions>
        <AppButton variant="ghost" :disabled="update.isPending.value" @click="save(requestedValue)">
          {{ t('projects.retry') }}
        </AppButton>
      </template>
    </AppFeedback>
  </ProjectOverviewSection>
</template>

<style scoped>
.game-mode-setting {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-5);
}

.game-mode-setting__copy {
  max-inline-size: 60ch;
}

.game-mode-setting__copy p,
.game-mode-setting__status {
  margin: 0;
}

.game-mode-setting__copy .game-mode-setting__retention {
  margin-block-start: var(--space-2);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.game-mode-setting__control {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--space-2);
  min-block-size: 2.75rem;
  font-weight: var(--weight-semibold);
  cursor: pointer;
}

.game-mode-setting__control:has(input:disabled) {
  cursor: wait;
  opacity: 0.7;
}

.game-mode-setting__control input {
  inline-size: 1.125rem;
  block-size: 1.125rem;
  accent-color: var(--accent);
}

.game-mode-setting__status {
  margin-block-start: var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

@media (max-width: 36rem) {
  .game-mode-setting {
    flex-direction: column;
  }
}
</style>
