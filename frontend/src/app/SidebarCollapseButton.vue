<script setup lang="ts">
import { PhSidebarSimple } from '@phosphor-icons/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import { useUserPreferences } from '@/composables/useUserPreferences'

import SidebarTooltip from './SidebarTooltip.vue'

const { t } = useI18n()
const account = useUserPreferences()
const state = ref<'idle' | 'saved' | 'failure' | 'conflict'>('idle')
const reloading = ref(false)
const reloadFailed = ref(false)
let generation = 0

const collapsed = computed(() => account.preferences.value?.desktop_sidebar_collapsed ?? false)
const label = computed(() => (collapsed.value ? t('nav.expandSidebar') : t('nav.collapseSidebar')))
const disabled = computed(
  () =>
    !account.canAccess.value ||
    account.preferences.value === null ||
    account.query.isError.value ||
    account.isSaving.value ||
    reloading.value ||
    state.value === 'conflict',
)
const error = computed(() => {
  if (reloadFailed.value) return t('sidebarPreferences.reloadError')
  if (state.value === 'conflict') return t('sidebarPreferences.conflict')
  if (state.value === 'failure') return t('nav.collapseSaveError')
  return ''
})

watch(
  [account.principalId, account.canAccess],
  () => {
    generation += 1
    state.value = 'idle'
    reloading.value = false
    reloadFailed.value = false
  },
  { flush: 'sync' },
)

async function toggle(): Promise<void> {
  const saved = account.preferences.value
  if (disabled.value || saved === null) return
  const owner = generation
  const result = await account.save({
    expected_revision: saved.revision,
    desktop_sidebar_collapsed: !saved.desktop_sidebar_collapsed,
  })
  if (owner !== generation || result.status === 'discarded') return
  state.value = result.status === 'success' ? 'saved' : result.status
  reloadFailed.value = false
  if (
    result.status === 'failure' &&
    result.error instanceof ApiError &&
    result.error.code === 'password_change_required'
  ) {
    account.session.mustChangePassword = true
  }
}

async function reload(): Promise<void> {
  if (reloading.value || account.isSaving.value || !account.canAccess.value) return
  const owner = generation
  reloading.value = true
  reloadFailed.value = false
  const saved = await account.reload()
  if (owner !== generation) return
  reloading.value = false
  reloadFailed.value = saved === null
  if (saved !== null) state.value = 'idle'
}

function dismiss(): void {
  state.value = 'idle'
  reloadFailed.value = false
}
</script>

<template>
  <div v-if="account.canAccess.value" class="sidebar-collapse">
    <SidebarTooltip v-slot="{ triggerProps }" :text="label" :disabled="!collapsed || disabled">
      <button
        v-bind="triggerProps"
        class="sidebar-collapse-button"
        type="button"
        :aria-label="label"
        :aria-expanded="!collapsed"
        :disabled="disabled"
        @click="toggle"
      >
        <PhSidebarSimple :size="20" aria-hidden="true" />
        <span class="sidebar-collapse-label">{{ label }}</span>
      </button>
    </SidebarTooltip>
    <span class="sidebar-collapse-status" role="status" aria-live="polite">
      {{
        account.isSaving.value
          ? t('userSettings.states.saving')
          : state === 'saved'
            ? t('userSettings.states.saved')
            : ''
      }}
    </span>
    <div v-if="error" class="sidebar-collapse-error">
      <p role="alert">{{ error }}</p>
      <button type="button" :disabled="reloading || account.isSaving.value" @click="reload">
        {{ reloading ? t('userSettings.states.reloading') : t('userSettings.reloadSaved') }}
      </button>
      <button v-if="state !== 'conflict'" type="button" @click="dismiss">
        {{ t('nav.dismiss') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.sidebar-collapse {
  position: relative;
}

.sidebar-collapse-button {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  min-height: var(--space-10);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--text-secondary);
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.sidebar-collapse-button svg {
  flex-shrink: 0;
}

.sidebar-collapse-button:hover:not(:disabled) {
  background: var(--surface-1);
  color: var(--text-primary);
}

.sidebar-collapse-button:disabled {
  cursor: default;
}

.sidebar-collapse-status,
.sidebar-collapse-button[aria-expanded='false'] .sidebar-collapse-label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.sidebar-collapse-button[aria-expanded='false'] {
  justify-content: center;
  padding: var(--space-2);
}

.sidebar-collapse-error {
  position: absolute;
  z-index: 20;
  bottom: calc(100% + var(--space-2));
  left: 0;
  width: var(--sidebar-width);
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  color: var(--text-primary);
}

.sidebar-collapse-error p {
  margin: 0 0 var(--space-2);
}

.sidebar-collapse-error button {
  min-height: var(--space-10);
  padding: var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  cursor: pointer;
}

@media (width < 1080px) {
  .sidebar-collapse {
    display: none;
  }
}
</style>
