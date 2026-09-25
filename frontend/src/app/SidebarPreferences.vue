<script setup lang="ts">
import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/vue'
import { PhCaretDown, PhCaretUp, PhCheck, PhMoon, PhTranslate } from '@phosphor-icons/vue'
import { computed, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '@/api'
import { useLocale } from '@/composables/useLocale'
import { useTheme } from '@/composables/useTheme'
import { useUserPreferences, type UserPreferencesUpdate } from '@/composables/useUserPreferences'

import SidebarTooltip from './SidebarTooltip.vue'

withDefaults(
  defineProps<{
    desktopCollapsed?: boolean
    mobile?: boolean
    presentation?: 'sidebar' | 'header'
  }>(),
  { presentation: 'sidebar' },
)

const { t } = useI18n()
const locale = useLocale()
const theme = useTheme()
const preferences = useUserPreferences()
const { canAccess, principalId, accessState, isSaving } = preferences
const helpId = useId()
const saveState = ref<'idle' | 'saved' | 'failure' | 'conflict'>('idle')
const isReloading = ref(false)
const hasReloadError = ref(false)
let generation = 0

const isAnonymous = computed(() => accessState.value === 'signedOut')
const isTemporary = computed(() => !canAccess.value && !isAnonymous.value)
const isBusy = computed(() => isSaving.value || isReloading.value)
const hasReadError = computed(() => canAccess.value && preferences.query.isError.value)
const disabled = computed(
  () =>
    canAccess.value &&
    (preferences.preferences.value === null ||
      isBusy.value ||
      saveState.value === 'conflict' ||
      hasReadError.value),
)

const controls = computed(() => [
  {
    key: 'locale',
    label: t('locale.label'),
    icon: PhTranslate,
    value: canAccess.value
      ? (preferences.preferences.value?.locale ?? 'browser')
      : locale.current.value,
    options: canAccess.value
      ? [{ value: 'browser', label: t('userSettings.language.browserDefault') }, ...locale.options]
      : locale.options,
    change: chooseLocale,
  },
  {
    key: 'theme',
    label: t('theme.label'),
    icon: PhMoon,
    value: canAccess.value
      ? (preferences.preferences.value?.theme ?? 'system')
      : theme.preference.value,
    options: [
      { value: 'system', label: t('theme.system') },
      { value: 'light', label: t('theme.light') },
      { value: 'dark', label: t('theme.dark') },
    ],
    change: chooseTheme,
  },
])

const statusMessage = computed(() => {
  if (!canAccess.value) return ''
  if (isSaving.value) return t('userSettings.states.saving')
  if (isReloading.value) return t('userSettings.states.reloading')
  if (preferences.preferences.value === null && !hasReadError.value)
    return t('userSettings.loading')
  if (saveState.value === 'saved') return t('userSettings.states.saved')
  return ''
})
const errorMessage = computed(() => {
  if (!canAccess.value) return ''
  if (hasReloadError.value) return t('sidebarPreferences.reloadError')
  if (saveState.value === 'conflict') return t('sidebarPreferences.conflict')
  if (saveState.value === 'failure') return t('sidebarPreferences.saveError')
  if (hasReadError.value) return t('userSettings.loadError')
  return ''
})
const canReload = computed(
  () =>
    hasReadError.value ||
    hasReloadError.value ||
    saveState.value === 'conflict' ||
    saveState.value === 'failure',
)

watch(
  [principalId, canAccess],
  () => {
    generation += 1
    saveState.value = 'idle'
    isReloading.value = false
    hasReloadError.value = false
  },
  { flush: 'sync' },
)

function enforcePasswordChange(error: unknown): void {
  if (error instanceof ApiError && error.code === 'password_change_required') {
    preferences.session.mustChangePassword = true
  }
}

watch(() => preferences.query.error.value, enforcePasswordChange)

function chooseLocale(value: string): void {
  if (disabled.value) return
  if (value !== 'de' && value !== 'en' && value !== 'browser') return
  if (canAccess.value) {
    void save({ locale: value === 'browser' ? null : value })
  } else if (value !== 'browser') {
    if (isAnonymous.value) locale.setLocale(value)
    else locale.applyLocale(value)
  }
}

function chooseTheme(value: string): void {
  if (disabled.value) return
  if (value !== 'system' && value !== 'light' && value !== 'dark') return
  if (canAccess.value) void save({ theme: value })
  else if (isAnonymous.value) theme.setPreference(value)
  else theme.applyPreference(value)
}

async function save(change: Omit<UserPreferencesUpdate, 'expected_revision'>): Promise<void> {
  const saved = preferences.preferences.value
  if (!canAccess.value || disabled.value || saved === null) return
  const requestGeneration = generation
  const result = await preferences.save({ ...change, expected_revision: saved.revision })
  if (requestGeneration !== generation || !canAccess.value) return
  if (result.status === 'success') {
    saveState.value = 'saved'
    hasReloadError.value = false
  } else if (result.status === 'conflict') {
    saveState.value = 'conflict'
  } else if (result.status === 'failure') {
    enforcePasswordChange(result.error)
    saveState.value = 'failure'
  }
  // The shared presentation observer alone applies canonical responses. Settings-page drafts
  // belong to that view and are never copied into or replaced by this immediate-save control.
}

async function reload(): Promise<void> {
  if (!canAccess.value || isBusy.value) return
  const requestGeneration = generation
  isReloading.value = true
  hasReloadError.value = false
  const saved = await preferences.reload()
  if (requestGeneration !== generation || !canAccess.value) return
  isReloading.value = false
  if (saved === null) hasReloadError.value = true
  else saveState.value = 'idle'
}
</script>

<template>
  <section
    class="sidebar-preferences"
    :class="{
      'sidebar-preferences--collapsed': presentation === 'sidebar' && desktopCollapsed && !mobile,
      'sidebar-preferences--mobile': presentation === 'sidebar' && mobile,
      'sidebar-preferences--header': presentation === 'header',
    }"
    :aria-label="t('sidebarPreferences.title')"
    :aria-busy="isBusy"
  >
    <Listbox
      v-for="control in controls"
      :key="control.key"
      v-slot="{ open }"
      as="div"
      class="sidebar-preferences-field"
      :data-preference="control.key"
      :model-value="control.value"
      :disabled="disabled"
      @update:model-value="control.change"
    >
      <SidebarTooltip
        v-slot="{ triggerProps }"
        :text="control.label"
        rail-only
        :desktop-collapsed="desktopCollapsed"
        :mobile="mobile"
        :disabled="open || presentation === 'header'"
      >
        <ListboxButton
          v-bind="triggerProps"
          class="sidebar-preferences-button"
          :aria-label="control.label"
          :aria-describedby="
            [triggerProps['aria-describedby'], isTemporary ? helpId : undefined]
              .filter(Boolean)
              .join(' ') || undefined
          "
        >
          <component :is="control.icon" :size="20" aria-hidden="true" />
          <span class="sidebar-preferences-copy">
            <span class="sidebar-preferences-label">{{ control.label }}</span>
            <span class="sidebar-preferences-value">{{
              control.options.find((option) => option.value === control.value)?.label
            }}</span>
          </span>
          <component
            :is="presentation === 'header' ? PhCaretDown : PhCaretUp"
            class="sidebar-preferences-caret"
            :size="14"
            aria-hidden="true"
          />
        </ListboxButton>
      </SidebarTooltip>
      <ListboxOptions class="sidebar-preferences-options" :aria-label="control.label">
        <ListboxOption
          v-for="option in control.options"
          :key="option.value"
          v-slot="{ active, selected }"
          :value="option.value"
          as="template"
        >
          <li
            class="sidebar-preferences-option"
            :class="{ 'sidebar-preferences-option--active': active }"
          >
            <span>{{ option.label }}</span>
            <PhCheck v-if="selected" :size="16" aria-hidden="true" />
          </li>
        </ListboxOption>
      </ListboxOptions>
    </Listbox>
    <p v-if="isTemporary" :id="helpId" class="sidebar-preferences-help">
      {{ t('sidebarPreferences.temporary') }}
    </p>
    <p class="sidebar-preferences-status" role="status" aria-live="polite" aria-atomic="true">
      {{ statusMessage }}
    </p>
    <div v-if="errorMessage" class="sidebar-preferences-feedback">
      <p class="sidebar-preferences-error" role="alert">{{ errorMessage }}</p>
      <button
        v-if="canReload"
        type="button"
        class="sidebar-preferences-retry"
        :disabled="isBusy"
        @click="reload"
      >
        {{
          saveState === 'conflict' || saveState === 'failure'
            ? t('userSettings.reloadSaved')
            : t('userSettings.retry')
        }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.sidebar-preferences {
  position: relative;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  gap: var(--space-2);
  min-width: 0;
  margin-top: auto;
  padding-top: var(--space-3);
  border-top: 1px solid var(--border);
}

.sidebar-preferences-field {
  position: relative;
  min-width: 0;
}

.sidebar-preferences-button {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  min-height: 2.75rem;
  padding: var(--space-2);
  border: 0;
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--text-primary);
  text-align: start;
  font: inherit;
  cursor: pointer;
}

.sidebar-preferences-button:hover:not(:disabled) {
  background: var(--surface-1);
}
.sidebar-preferences-button:disabled {
  color: var(--muted);
  cursor: wait;
}
.sidebar-preferences-button > svg {
  flex-shrink: 0;
}
.sidebar-preferences-copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}
.sidebar-preferences-label {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}
.sidebar-preferences-value {
  font-size: var(--font-size-body);
  overflow-wrap: anywhere;
}

.sidebar-preferences-options {
  position: absolute;
  z-index: 20;
  inset-inline-start: 0;
  bottom: calc(100% + var(--space-1));
  width: max-content;
  min-width: min(max(100%, 12rem), calc(100vw - 2 * var(--space-4)));
  max-width: calc(100vw - 2 * var(--space-4));
  max-height: min(18rem, 60dvh);
  overflow-y: auto;
  margin: 0;
  padding: var(--space-1);
  border-radius: var(--radius-control);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
  list-style: none;
}

.sidebar-preferences-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  color: var(--text-primary);
  font-size: var(--font-size-body);
  overflow-wrap: anywhere;
  cursor: pointer;
}

.sidebar-preferences-option--active {
  background: var(--surface-1);
}
.sidebar-preferences-option[aria-selected='true'] {
  color: var(--accent);
  font-weight: var(--weight-semibold);
}
.sidebar-preferences-option svg {
  flex-shrink: 0;
}
.sidebar-preferences-help,
.sidebar-preferences-status,
.sidebar-preferences-error {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  overflow-wrap: anywhere;
}
.sidebar-preferences-status:empty {
  display: none;
}
.sidebar-preferences-error {
  color: var(--text-primary);
}
.sidebar-preferences-retry {
  min-height: 2.75rem;
  padding: var(--space-1) 0;
  border: 0;
  background: none;
  color: var(--accent);
  text-align: start;
  font: inherit;
  cursor: pointer;
}
.sidebar-preferences-retry:disabled {
  color: var(--muted);
  cursor: wait;
}

.sidebar-preferences--collapsed .sidebar-preferences-copy,
.sidebar-preferences--collapsed .sidebar-preferences-help,
.sidebar-preferences--collapsed .sidebar-preferences-status {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.sidebar-preferences--collapsed .sidebar-preferences-caret {
  display: none;
}
.sidebar-preferences--collapsed .sidebar-preferences-button {
  justify-content: center;
}
.sidebar-preferences--collapsed .sidebar-preferences-feedback {
  position: absolute;
  z-index: 20;
  inset-inline-start: calc(100% + var(--space-3));
  bottom: 0;
  width: min(20rem, calc(100vw - 6rem));
  padding: var(--space-3);
  border-radius: var(--radius-control);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
}

.sidebar-preferences--header {
  flex-direction: row;
  flex-wrap: wrap;
  flex-shrink: 1;
  align-items: center;
  max-width: 100%;
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}

.sidebar-preferences--header .sidebar-preferences-field {
  position: static;
  max-width: 100%;
}

.sidebar-preferences--header .sidebar-preferences-button {
  width: auto;
  min-width: var(--control-min-size);
  min-height: var(--control-min-size);
  max-width: 100%;
}

.sidebar-preferences--header .sidebar-preferences-copy {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: baseline;
  column-gap: var(--space-2);
}

.sidebar-preferences--header .sidebar-preferences-label {
  overflow-wrap: anywhere;
}

.sidebar-preferences--header .sidebar-preferences-value {
  font-size: var(--font-size-small);
}

.sidebar-preferences--header .sidebar-preferences-options {
  /* Bound both popups to the wrapping preference group, wherever it sits in the header. */
  top: calc(100% + var(--space-1));
  bottom: auto;
  inset-inline-start: auto;
  inset-inline-end: 0;
  min-width: min(12rem, 100%);
  max-width: min(24rem, 100%);
}

.sidebar-preferences--header .sidebar-preferences-help,
.sidebar-preferences--header .sidebar-preferences-status,
.sidebar-preferences--header .sidebar-preferences-feedback {
  flex-basis: 100%;
  min-width: 0;
}

@media (width < 720px) {
  .sidebar-preferences--header .sidebar-preferences-field {
    flex: 1 1 0;
  }

  .sidebar-preferences--header .sidebar-preferences-button {
    width: 100%;
  }

  .sidebar-preferences--header .sidebar-preferences-copy {
    flex-direction: column;
    align-items: stretch;
  }
}

@media (720px <= width < 1080px) {
  .sidebar-preferences:not(.sidebar-preferences--mobile, .sidebar-preferences--header)
    .sidebar-preferences-copy,
  .sidebar-preferences:not(.sidebar-preferences--mobile, .sidebar-preferences--header)
    .sidebar-preferences-help,
  .sidebar-preferences:not(.sidebar-preferences--mobile, .sidebar-preferences--header)
    .sidebar-preferences-status {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .sidebar-preferences:not(.sidebar-preferences--mobile, .sidebar-preferences--header)
    .sidebar-preferences-caret {
    display: none;
  }
  .sidebar-preferences:not(.sidebar-preferences--mobile, .sidebar-preferences--header)
    .sidebar-preferences-button {
    justify-content: center;
  }
  .sidebar-preferences:not(.sidebar-preferences--mobile, .sidebar-preferences--header)
    .sidebar-preferences-feedback {
    position: absolute;
    z-index: 20;
    inset-inline-start: calc(100% + var(--space-3));
    bottom: 0;
    width: min(20rem, calc(100vw - 6rem));
    padding: var(--space-3);
    border-radius: var(--radius-control);
    background: var(--panel);
    box-shadow: var(--shadow-menu);
  }
}
</style>
