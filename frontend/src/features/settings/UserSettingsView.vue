<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import { useUserPreferences, type UserPreferences } from '@/composables/useUserPreferences'

type PreferencesDraft = Omit<UserPreferences, 'revision'>

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const preferences = useUserPreferences()
const { accessState, principalId, canAccess, isSaving } = preferences
const baseline = ref<UserPreferences | null>(null)
const draft = ref<PreferencesDraft | null>(null)
const saveState = ref<'idle' | 'saved' | 'failure' | 'conflict'>('idle')
const isReloading = ref(false)
const hasReloadError = ref(false)
let draftGeneration = 0

const hasChanges = computed(
  () =>
    baseline.value !== null &&
    draft.value !== null &&
    (baseline.value.locale !== draft.value.locale ||
      baseline.value.theme !== draft.value.theme ||
      baseline.value.desktop_sidebar_collapsed !== draft.value.desktop_sidebar_collapsed),
)
const isBusy = computed(() => isSaving.value || isReloading.value)
const canSave = computed(
  () => canAccess.value && hasChanges.value && !isBusy.value && saveState.value !== 'conflict',
)
const hasReadError = computed(() => canAccess.value && preferences.query.isError.value)
const statusMessage = computed(() => {
  if (accessState.value === 'loading') return t('userSettings.loadingAccess')
  if (!canAccess.value) return ''
  if (isReloading.value) return t('userSettings.states.reloading')
  if (isSaving.value) return t('userSettings.states.saving')
  if (baseline.value === null && !hasReadError.value) return t('userSettings.loading')
  if (baseline.value === null) return ''
  if (hasChanges.value) return t('userSettings.states.unsaved')
  if (saveState.value === 'saved') return t('userSettings.states.saved')
  return t('userSettings.states.unchanged')
})
const errorMessage = computed(() => {
  if (accessState.value === 'sessionError') return t('userSettings.sessionLoadError')
  if (!canAccess.value) return ''
  if (hasReloadError.value) return t('userSettings.reloadError')
  if (saveState.value === 'conflict') return t('userSettings.conflict')
  if (saveState.value === 'failure') return t('userSettings.saveError')
  if (hasReadError.value) return t('userSettings.loadError')
  return ''
})

function adoptSaved(values: UserPreferences): void {
  baseline.value = { ...values }
  draft.value = {
    locale: values.locale,
    theme: values.theme,
    desktop_sidebar_collapsed: values.desktop_sidebar_collapsed,
  }
}

watch(
  [principalId, canAccess],
  ([owner], [previousOwner]) => {
    draftGeneration += 1
    isReloading.value = false
    if (owner !== previousOwner || preferences.session.mustChangePassword) {
      baseline.value = null
      draft.value = null
      saveState.value = 'idle'
      hasReloadError.value = false
    }
  },
  { flush: 'sync' },
)

watch(
  [canAccess, preferences.preferences],
  ([isEligible, values]) => {
    // Only initialize a new draft. Background refetches must never replace unsaved input.
    if (isEligible && values !== null && baseline.value === null) adoptSaved(values)
  },
  { immediate: true },
)

watch(
  accessState,
  (state) => {
    if (state === 'signedOut') {
      void router.replace({ name: 'login', query: { redirect: route.fullPath } })
    } else if (state === 'passwordChangeRequired') {
      void router.replace({ name: 'changePassword', query: { redirect: route.fullPath } })
    }
  },
  { immediate: true },
)

watch(
  () => preferences.query.error.value,
  (error) => enforcePasswordChange(error),
)

function enforcePasswordChange(error: unknown): void {
  if (error instanceof ApiError && error.code === 'password_change_required') {
    preferences.session.mustChangePassword = true
  }
}

function restoreDefaults(): void {
  if (draft.value === null || isBusy.value) return
  draft.value = { locale: null, theme: 'system', desktop_sidebar_collapsed: false }
}

async function save(): Promise<void> {
  if (!canSave.value || draft.value === null || baseline.value === null) return
  const generation = draftGeneration
  const result = await preferences.save({
    ...draft.value,
    expected_revision: baseline.value.revision,
  })
  if (generation !== draftGeneration || !canAccess.value) return
  switch (result.status) {
    case 'success':
      adoptSaved(result.preferences)
      hasReloadError.value = false
      saveState.value = 'saved'
      break
    case 'conflict':
      saveState.value = 'conflict'
      break
    case 'failure':
      enforcePasswordChange(result.error)
      saveState.value = 'failure'
      break
    case 'discarded':
      break
  }
}

async function retryRead(): Promise<void> {
  await loadSaved(false)
}

async function reloadSaved(): Promise<void> {
  await loadSaved(true)
}

async function loadSaved(replaceDraft: boolean): Promise<void> {
  if (!canAccess.value || isBusy.value) return
  const generation = draftGeneration
  isReloading.value = true
  hasReloadError.value = false
  const values = await preferences.reload()
  if (generation !== draftGeneration || !canAccess.value) return
  isReloading.value = false
  if (values === null) {
    hasReloadError.value = true
    return
  }
  if (replaceDraft || baseline.value === null) {
    adoptSaved(values)
    saveState.value = 'idle'
  }
}
</script>

<template>
  <main class="user-settings">
    <header class="user-settings-heading">
      <h1>{{ t('userSettings.title') }}</h1>
      <p>{{ t('userSettings.description') }}</p>
    </header>

    <p class="user-settings-status" role="status" aria-live="polite" aria-atomic="true">
      {{ statusMessage }}
    </p>
    <p class="user-settings-error" role="alert" aria-atomic="true">{{ errorMessage }}</p>

    <AppButton
      v-if="accessState === 'sessionError'"
      variant="ghost"
      @click="preferences.session.initialize()"
    >
      {{ t('userSettings.retry') }}
    </AppButton>

    <template v-if="canAccess">
      <div
        v-if="baseline === null && !hasReadError"
        class="user-settings-skeleton"
        aria-hidden="true"
      >
        <div></div>
        <div></div>
        <div></div>
      </div>

      <AppButton
        v-if="hasReadError && saveState !== 'conflict'"
        variant="ghost"
        :disabled="isBusy"
        @click="retryRead"
      >
        {{ t('userSettings.retry') }}
      </AppButton>

      <form v-if="draft !== null" :aria-busy="isBusy" @submit.prevent="save">
        <fieldset :disabled="isBusy" :aria-label="t('userSettings.title')">
          <div class="user-settings-field">
            <label for="user-settings-locale">{{ t('userSettings.language.label') }}</label>
            <p id="user-settings-locale-help">{{ t('userSettings.language.description') }}</p>
            <select
              id="user-settings-locale"
              v-model="draft.locale"
              aria-describedby="user-settings-locale-help"
            >
              <option :value="null">{{ t('userSettings.language.browserDefault') }}</option>
              <option value="de" lang="de">{{ t('userSettings.language.de') }}</option>
              <option value="en" lang="en">{{ t('userSettings.language.en') }}</option>
            </select>
          </div>

          <div class="user-settings-field">
            <label for="user-settings-theme">{{ t('userSettings.theme.label') }}</label>
            <p id="user-settings-theme-help">{{ t('userSettings.theme.description') }}</p>
            <select
              id="user-settings-theme"
              v-model="draft.theme"
              aria-describedby="user-settings-theme-help"
            >
              <option value="system">{{ t('userSettings.theme.system') }}</option>
              <option value="light">{{ t('userSettings.theme.light') }}</option>
              <option value="dark">{{ t('userSettings.theme.dark') }}</option>
            </select>
          </div>

          <div class="user-settings-field">
            <label for="user-settings-sidebar">{{ t('userSettings.sidebar.label') }}</label>
            <p id="user-settings-sidebar-help">{{ t('userSettings.sidebar.description') }}</p>
            <select
              id="user-settings-sidebar"
              v-model="draft.desktop_sidebar_collapsed"
              aria-describedby="user-settings-sidebar-help"
            >
              <option :value="false">{{ t('userSettings.sidebar.expanded') }}</option>
              <option :value="true">{{ t('userSettings.sidebar.collapsed') }}</option>
            </select>
          </div>
        </fieldset>

        <div v-if="saveState === 'conflict'" class="user-settings-conflict">
          <p>{{ t('userSettings.conflictReloadHint') }}</p>
          <AppButton variant="ghost" :disabled="isBusy" @click="reloadSaved">
            {{ t('userSettings.reloadSaved') }}
          </AppButton>
        </div>

        <footer class="user-settings-actions">
          <p>{{ t('userSettings.saveHint') }}</p>
          <div>
            <AppButton type="submit" :disabled="!canSave">{{ t('userSettings.save') }}</AppButton>
            <AppButton variant="ghost" :disabled="isBusy" @click="restoreDefaults">
              {{ t('userSettings.restoreDefaults') }}
            </AppButton>
          </div>
        </footer>
      </form>
    </template>
  </main>
</template>

<style scoped>
.user-settings {
  flex: 1;
  min-width: 0;
  width: 100%;
  max-width: 48rem;
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
}

.user-settings-heading h1 {
  margin: 0;
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
}

.user-settings-heading p {
  max-width: 65ch;
  margin: var(--space-2) 0 var(--space-5);
  color: var(--text-secondary);
}

.user-settings-status {
  min-height: var(--space-5);
  margin: 0 0 var(--space-4);
  color: var(--text-secondary);
}

.user-settings-error {
  margin: 0 0 var(--space-4);
  color: var(--critical);
}

.user-settings-error:empty {
  margin: 0;
}

.user-settings fieldset {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.user-settings-field {
  padding: var(--space-5) 0;
  border-top: 1px solid var(--grid);
}

.user-settings-field label {
  display: block;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.user-settings-field p,
.user-settings-actions > p {
  margin: var(--space-1) 0 var(--space-3);
  color: var(--text-secondary);
}

.user-settings-field select {
  width: 100%;
  max-width: 22rem;
  min-height: var(--space-10);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
}

.user-settings-field select:disabled {
  cursor: wait;
}

.user-settings-actions {
  padding-top: var(--space-5);
  border-top: 1px solid var(--grid);
}

.user-settings-actions > div {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.user-settings-conflict {
  padding: var(--space-4);
  margin-bottom: var(--space-5);
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--surface-1);
}

.user-settings-conflict p {
  margin: 0 0 var(--space-3);
  color: var(--text-secondary);
}

.user-settings-skeleton {
  display: grid;
  gap: var(--space-6);
}

.user-settings-skeleton div {
  height: 7rem;
  border-radius: var(--radius-input);
  background: var(--surface-1);
}
</style>
