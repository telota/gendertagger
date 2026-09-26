<script setup lang="ts">
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { components } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import { useDraftRegistration } from '@/composables/useDraftNavigation'

import type { AdminSettings } from './useAdminSettings'
import type { AdminSettingsMutationError } from './useAdminSettingsMutations'

type EditableBrandingValues = components['schemas']['BrandingEditableValues']
type EditableBrandingField = keyof EditableBrandingValues
type FieldMode = 'unchanged' | 'set' | 'clear'
type BrandingValue = string | number | string[] | null | undefined

const EDITABLE_BRANDING_FIELDS = [
  'institution_name',
  'institution_url',
  'contact_email',
  'privacy_notice_url',
  'editors',
  'published_since_year',
] as const satisfies readonly EditableBrandingField[]

const props = defineProps<{
  settings: AdminSettings
  isSubmitting: boolean
  mutationError: AdminSettingsMutationError | null
  hasConflict: boolean
  conflictLatest: AdminSettings | null
}>()

const emit = defineEmits<{
  save: [command: components['schemas']['AdminSettingsUpdate']]
  reset: [command: components['schemas']['AdminSettingsReset']]
  discardDraft: []
  reconcileConflict: []
}>()

const { t } = useI18n()
const baseline = ref(props.settings)
const modes = ref<Record<EditableBrandingField, FieldMode>>({
  institution_name: 'unchanged',
  institution_url: 'unchanged',
  contact_email: 'unchanged',
  privacy_notice_url: 'unchanged',
  editors: 'unchanged',
  published_since_year: 'unchanged',
})
const values = ref<Record<EditableBrandingField, string>>({
  institution_name: stringValue(props.settings.branding.institution_name),
  institution_url: stringValue(props.settings.branding.institution_url),
  contact_email: stringValue(props.settings.branding.contact_email),
  privacy_notice_url: stringValue(props.settings.branding.privacy_notice_url),
  editors: (props.settings.branding.editors ?? []).join('\n'),
  published_since_year: stringValue(props.settings.branding.published_since_year),
})
const hasSubmitted = ref(false)
const resetFields = ref<EditableBrandingField[]>([])
const isResetConfirmationOpen = ref(false)
const activeField = ref<EditableBrandingField | null>(null)

const changedFields = computed(() =>
  EDITABLE_BRANDING_FIELDS.filter((field) => modes.value[field] !== 'unchanged'),
)
const hasChanges = computed(() => changedFields.value.length > 0)
useDraftRegistration(
  () => hasChanges.value || resetFields.value.length > 0,
  () => {
    for (const field of EDITABLE_BRANDING_FIELDS) modes.value[field] = 'unchanged'
    resetFields.value = []
    isResetConfirmationOpen.value = false
    activeField.value = null
    discardDraft()
  },
)
const hasValidationErrors = computed(() =>
  EDITABLE_BRANDING_FIELDS.some((field) => fieldError(field) !== undefined),
)
const selectedResetFallbacks = computed(() =>
  resetFields.value.map((field) => ({ field, value: fallbackValue(field) })),
)

function stringValue(value: string | number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value)
}

function fieldLabel(field: EditableBrandingField): string {
  switch (field) {
    case 'institution_name':
      return t('adminSettings.fields.institutionName')
    case 'institution_url':
      return t('adminSettings.fields.institutionUrl')
    case 'contact_email':
      return t('adminSettings.fields.contactEmail')
    case 'privacy_notice_url':
      return t('adminSettings.fields.privacyNoticeUrl')
    case 'editors':
      return t('adminSettings.fields.editors')
    case 'published_since_year':
      return t('adminSettings.fields.publishedSinceYear')
  }
}

function fallbackValue(field: EditableBrandingField): string {
  const value = props.settings.branding_defaults[field]
  if (Array.isArray(value))
    return value.length === 0 ? t('adminSettings.values.noEditors') : value.join(', ')
  return value === null ? t('adminSettings.values.notConfigured') : String(value)
}

function effectiveValue(field: EditableBrandingField): BrandingValue {
  return props.settings.branding[field]
}

function formatValue(value: BrandingValue): string {
  if (Array.isArray(value)) {
    return value.length === 0 ? t('adminSettings.values.noEditors') : value.join(', ')
  }
  if (value === null || value === undefined || value === '') {
    return t('adminSettings.values.notConfigured')
  }
  return String(value)
}

function isOverridden(field: EditableBrandingField): boolean {
  return props.settings.overridden_fields.includes(field)
}

function isCleared(field: EditableBrandingField): boolean {
  if (!isOverridden(field)) return false
  const value = effectiveValue(field)
  return value === null || (Array.isArray(value) && value.length === 0)
}

function displayValue(field: EditableBrandingField): string {
  const mode = modes.value[field]
  if (mode === 'unchanged') {
    return isCleared(field)
      ? t('adminSettings.values.noPublishedValue')
      : formatValue(effectiveValue(field))
  }
  if (mode === 'clear') return t('adminSettings.values.noPublishedValue')
  if (field === 'editors') {
    const editors = values.value.editors
      .split('\n')
      .map((editor) => editor.trim())
      .filter(Boolean)
    return editors.length === 0 ? t('adminSettings.values.noEditors') : editors.join(', ')
  }
  return formatValue(values.value[field].trim())
}

function overrideStatus(field: EditableBrandingField): string {
  if (modes.value[field] !== 'unchanged') return t('adminSettings.editing.pendingChange')
  if (!isOverridden(field)) return t('adminSettings.status.inherited')
  return isCleared(field) ? t('adminSettings.status.cleared') : t('adminSettings.status.overridden')
}

function overrideStatusClass(field: EditableBrandingField): string {
  if (modes.value[field] !== 'unchanged') return 'admin-settings-status--pending'
  if (isCleared(field)) return 'admin-settings-status--cleared'
  return isOverridden(field)
    ? 'admin-settings-status--overridden'
    : 'admin-settings-status--inherited'
}

function toggleField(field: EditableBrandingField): void {
  activeField.value = activeField.value === field ? null : field
}

const CONTACT_EMAIL_PATTERN =
  /^(?=.{1,254}$)(?=.{1,64}@)[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$/

function hasControlCharacters(value: string): boolean {
  return [...value].some((character) => {
    const codePoint = character.codePointAt(0)
    return codePoint !== undefined && (codePoint <= 31 || (codePoint >= 127 && codePoint <= 159))
  })
}

function isValidUrl(value: string): boolean {
  if (/\s|\\/.test(value) || hasControlCharacters(value)) return false
  if (value.startsWith('/')) return !value.startsWith('//')
  try {
    const url = new URL(value)
    return (url.protocol === 'http:' || url.protocol === 'https:') && !url.username && !url.password
  } catch {
    return false
  }
}

function editorsValue(): string[] {
  return values.value.editors.split('\n').map((editor) => editor.trim())
}

function fieldError(field: EditableBrandingField): string | undefined {
  if (!hasSubmitted.value || modes.value[field] !== 'set') return undefined
  const value = values.value[field]
  switch (field) {
    case 'institution_name': {
      const normalized = value.trim()
      return normalized.length === 0 || normalized.length > 200 || hasControlCharacters(value)
        ? t('adminSettings.editing.validation.institutionName')
        : undefined
    }
    case 'institution_url':
    case 'privacy_notice_url':
      return value.length > 2048 || !isValidUrl(value)
        ? t('adminSettings.editing.validation.url')
        : undefined
    case 'contact_email':
      return value.length > 254 || hasControlCharacters(value) || !CONTACT_EMAIL_PATTERN.test(value)
        ? t('adminSettings.editing.validation.contactEmail')
        : undefined
    case 'editors': {
      const editors = editorsValue()
      const hasInvalidEditor = editors.some(
        (editor) => editor.length === 0 || editor.length > 200 || hasControlCharacters(editor),
      )
      return editors.length > 50 || hasInvalidEditor || new Set(editors).size !== editors.length
        ? t('adminSettings.editing.validation.editors')
        : undefined
    }
    case 'published_since_year': {
      const year = Number(value)
      const currentYear = new Date().getUTCFullYear()
      return !/^\d+$/.test(value) || !Number.isInteger(year) || year < 1 || year > currentYear
        ? t('adminSettings.editing.validation.publishedSinceYear', { currentYear })
        : undefined
    }
  }
}

function updateMode(field: EditableBrandingField): void {
  if (modes.value[field] === 'set') return
  modes.value[field] = 'set'
}

function buildBrandingOverrides(): components['schemas']['BrandingOverrides'] {
  const branding: components['schemas']['BrandingOverrides'] = {}
  for (const field of EDITABLE_BRANDING_FIELDS) {
    if (modes.value[field] === 'unchanged') continue
    switch (field) {
      case 'institution_name':
      case 'institution_url':
      case 'contact_email':
      case 'privacy_notice_url':
        branding[field] = modes.value[field] === 'clear' ? null : values.value[field]
        break
      case 'editors':
        branding.editors = modes.value[field] === 'clear' ? [] : editorsValue()
        break
      case 'published_since_year':
        branding.published_since_year =
          modes.value[field] === 'clear' ? null : Number(values.value[field])
        break
    }
  }
  return branding
}

function submit(): void {
  hasSubmitted.value = true
  if (!hasChanges.value || hasValidationErrors.value || props.isSubmitting || props.hasConflict)
    return
  emit('save', {
    expected_revision: baseline.value.revision,
    branding: buildBrandingOverrides(),
  })
}

function openResetConfirmation(): void {
  if (hasChanges.value || resetFields.value.length === 0 || props.isSubmitting || props.hasConflict)
    return
  isResetConfirmationOpen.value = true
}

function confirmReset(): void {
  isResetConfirmationOpen.value = false
  emit('reset', { expected_revision: baseline.value.revision, fields: [...resetFields.value] })
}

function discardDraft(): void {
  emit('discardDraft')
}

function reconcileConflict(): void {
  const latest = props.conflictLatest
  if (latest === null) return
  baseline.value = latest
  emit('reconcileConflict')
}

function errorMessage(error: AdminSettingsMutationError | null): string | null {
  switch (error) {
    case 'settings_unavailable':
      return t('adminSettings.editing.errors.settingsUnavailable')
    case 'validation_error':
      return t('adminSettings.editing.errors.validation')
    case 'authentication_required':
      return t('adminSettings.editing.errors.authenticationRequired')
    case 'password_change_required':
      return t('adminSettings.editing.errors.passwordChangeRequired')
    case 'forbidden':
      return t('adminSettings.editing.errors.forbidden')
    case 'network_error':
      return t('adminSettings.editing.errors.uncertain')
    case 'unexpected':
      return t('adminSettings.editing.errors.uncertain')
    case 'settings_revision_conflict':
    case null:
      return null
  }
}
</script>

<template>
  <section class="admin-settings-editor" aria-labelledby="admin-settings-editor-heading">
    <header class="admin-settings-editor-heading">
      <div>
        <h2 id="admin-settings-editor-heading">{{ t('adminSettings.editing.title') }}</h2>
        <p>{{ t('adminSettings.editing.description') }}</p>
      </div>
      <p class="admin-settings-editor-revision">
        {{ t('adminSettings.revision', { revision: settings.revision }) }}
      </p>
    </header>

    <p class="admin-settings-editor-precedence">
      {{ t('adminSettings.precedence.description') }}
    </p>

    <div v-if="hasConflict" class="admin-settings-editor-conflict" role="alert">
      <p v-if="conflictLatest">
        {{
          t('adminSettings.editing.conflict.latestLoaded', { revision: conflictLatest.revision })
        }}
      </p>
      <p v-else>{{ t('adminSettings.editing.conflict.latestUnavailable') }}</p>
      <div v-if="conflictLatest" class="admin-settings-editor-action-buttons">
        <AppButton type="button" @click="reconcileConflict">
          {{ t('adminSettings.editing.conflict.reconcile') }}
        </AppButton>
        <AppButton type="button" variant="ghost" @click="discardDraft">
          {{ t('adminSettings.editing.discard') }}
        </AppButton>
      </div>
    </div>

    <form novalidate class="admin-settings-editor-form" @submit.prevent="submit">
      <div class="admin-settings-editor-field-list">
        <section
          v-for="field in EDITABLE_BRANDING_FIELDS"
          :key="field"
          class="admin-settings-editor-field"
          :class="{ 'admin-settings-editor-field--changed': modes[field] !== 'unchanged' }"
          :aria-labelledby="`admin-settings-${field}-heading`"
        >
          <div class="admin-settings-editor-summary">
            <div class="admin-settings-editor-summary-copy">
              <h3 :id="`admin-settings-${field}-heading`">{{ fieldLabel(field) }}</h3>
              <p
                class="admin-settings-editor-value"
                :class="{ 'admin-settings-editor-value--cleared': isCleared(field) }"
              >
                {{ displayValue(field) }}
              </p>
              <p
                v-if="modes[field] === 'unchanged' && isOverridden(field)"
                class="admin-settings-editor-source"
              >
                {{ t('adminSettings.editing.fallback', { value: fallbackValue(field) }) }}
              </p>
            </div>
            <div class="admin-settings-editor-summary-actions">
              <span class="admin-settings-status" :class="overrideStatusClass(field)">
                {{ overrideStatus(field) }}
              </span>
              <AppButton
                type="button"
                variant="ghost"
                :aria-expanded="activeField === field"
                :aria-controls="`admin-settings-${field}-controls`"
                :aria-label="
                  activeField === field
                    ? t('adminSettings.editing.closeFieldLabel', { field: fieldLabel(field) })
                    : t('adminSettings.editing.changeFieldLabel', { field: fieldLabel(field) })
                "
                @click="toggleField(field)"
              >
                {{
                  activeField === field
                    ? t('adminSettings.editing.closeField')
                    : t('adminSettings.editing.changeField')
                }}
              </AppButton>
            </div>
          </div>

          <fieldset
            v-if="activeField === field"
            :id="`admin-settings-${field}-controls`"
            class="admin-settings-editor-controls"
          >
            <legend>
              {{ t('adminSettings.editing.changeFieldLabel', { field: fieldLabel(field) }) }}
            </legend>
            <p class="admin-settings-editor-fallback">
              {{ t('adminSettings.editing.fallback', { value: fallbackValue(field) }) }}
            </p>
            <div class="admin-settings-editor-mode">
              <label>
                <input
                  v-model="modes[field]"
                  type="radio"
                  :name="`${field}-mode`"
                  value="unchanged"
                />
                {{ t('adminSettings.editing.modes.unchanged') }}
              </label>
              <label>
                <input v-model="modes[field]" type="radio" :name="`${field}-mode`" value="set" />
                {{ t('adminSettings.editing.modes.set') }}
              </label>
              <label>
                <input v-model="modes[field]" type="radio" :name="`${field}-mode`" value="clear" />
                {{ t('adminSettings.editing.modes.clear') }}
              </label>
            </div>

            <div v-if="modes[field] === 'set'" class="admin-settings-editor-value-field">
              <label :for="`admin-settings-${field}`">
                {{ t('adminSettings.editing.valueFor', { field: fieldLabel(field) }) }}
              </label>
              <textarea
                v-if="field === 'editors'"
                :id="`admin-settings-${field}`"
                v-model="values[field]"
                :name="field"
                :aria-invalid="fieldError(field) ? true : undefined"
                :aria-describedby="fieldError(field) ? `admin-settings-${field}-error` : undefined"
                rows="5"
                @input="updateMode(field)"
              />
              <input
                v-else
                :id="`admin-settings-${field}`"
                v-model="values[field]"
                :name="field"
                :type="field === 'contact_email' ? 'email' : 'text'"
                :inputmode="field === 'published_since_year' ? 'numeric' : undefined"
                :maxlength="field === 'contact_email' ? 254 : field.includes('url') ? 2048 : 200"
                :aria-invalid="fieldError(field) ? true : undefined"
                :aria-describedby="fieldError(field) ? `admin-settings-${field}-error` : undefined"
                @input="updateMode(field)"
              />
              <p v-if="field === 'editors'" class="admin-settings-editor-hint">
                {{ t('adminSettings.editing.editorsHint') }}
              </p>
              <p v-if="fieldError(field)" :id="`admin-settings-${field}-error`" role="alert">
                {{ fieldError(field) }}
              </p>
            </div>
          </fieldset>
        </section>
      </div>

      <p v-if="errorMessage(mutationError)" role="alert" class="admin-settings-editor-error">
        {{ errorMessage(mutationError) }}
      </p>
      <div class="admin-settings-editor-actions">
        <p class="admin-settings-editor-change-summary" role="status">
          {{
            hasChanges
              ? t('adminSettings.editing.changesPending', { count: changedFields.length })
              : t('adminSettings.editing.noChanges')
          }}
        </p>
        <div class="admin-settings-editor-action-buttons">
          <AppButton type="submit" :disabled="!hasChanges || isSubmitting || hasConflict">
            {{
              isSubmitting ? t('adminSettings.editing.submitting') : t('adminSettings.editing.save')
            }}
          </AppButton>
          <AppButton
            type="button"
            variant="ghost"
            :disabled="!hasChanges || isSubmitting"
            @click="discardDraft"
          >
            {{ t('adminSettings.editing.discard') }}
          </AppButton>
        </div>
      </div>
    </form>

    <section
      v-if="settings.overridden_fields.length"
      class="admin-settings-reset"
      aria-labelledby="admin-settings-reset-heading"
    >
      <h3 id="admin-settings-reset-heading">{{ t('adminSettings.reset.title') }}</h3>
      <p>{{ t('adminSettings.reset.description') }}</p>
      <p v-if="hasChanges" class="admin-settings-reset-dirty">
        {{ t('adminSettings.reset.unsavedChanges') }}
      </p>
      <template v-else>
        <div
          v-for="field in settings.overridden_fields"
          :key="field"
          class="admin-settings-reset-field"
        >
          <input
            :id="`admin-settings-reset-${field}`"
            v-model="resetFields"
            type="checkbox"
            :value="field"
          />
          <label :for="`admin-settings-reset-${field}`">
            {{ fieldLabel(field) }}
            <span>{{ t('adminSettings.reset.fallback', { value: fallbackValue(field) }) }}</span>
          </label>
        </div>
        <AppButton
          type="button"
          tone="destructive"
          :disabled="resetFields.length === 0 || isSubmitting || hasConflict"
          @click="openResetConfirmation"
        >
          {{ t('adminSettings.reset.submit') }}
        </AppButton>
      </template>
    </section>

    <Dialog
      :open="isResetConfirmationOpen"
      class="admin-settings-reset-dialog"
      @close="isResetConfirmationOpen = false"
    >
      <div class="admin-settings-reset-backdrop" aria-hidden="true" />
      <div class="admin-settings-reset-frame">
        <DialogPanel class="admin-settings-reset-panel">
          <DialogTitle class="admin-settings-reset-title">{{
            t('adminSettings.reset.confirm.title')
          }}</DialogTitle>
          <p>{{ t('adminSettings.reset.confirm.description') }}</p>
          <ul>
            <li v-for="item in selectedResetFallbacks" :key="item.field">
              {{
                t('adminSettings.reset.confirm.entry', {
                  field: fieldLabel(item.field),
                  value: item.value,
                })
              }}
            </li>
          </ul>
          <p>{{ t('adminSettings.reset.confirm.nonAtomic') }}</p>
          <div class="admin-settings-editor-action-buttons">
            <AppButton type="button" variant="ghost" @click="isResetConfirmationOpen = false">
              {{ t('adminSettings.reset.confirm.cancel') }}
            </AppButton>
            <AppButton type="button" tone="destructive" @click="confirmReset">
              {{ t('adminSettings.reset.confirm.submit') }}
            </AppButton>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  </section>
</template>

<style scoped>
.admin-settings-editor {
  container: branding-editor / inline-size;
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.admin-settings-editor h2,
.admin-settings-editor h3 {
  margin: 0;
  color: var(--text-primary);
  font-weight: var(--weight-semibold);
}

.admin-settings-editor h2 {
  font-size: var(--font-size-title);
}

.admin-settings-editor h3 {
  font-size: var(--font-size-body-strong);
}

.admin-settings-editor-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-5) var(--space-5) var(--space-2);
}

.admin-settings-editor-heading p,
.admin-settings-editor-precedence,
.admin-settings-editor-fallback,
.admin-settings-editor-hint,
.admin-settings-editor-source,
.admin-settings-reset > p {
  margin: var(--space-2) 0 0;
  color: var(--text-secondary);
}

.admin-settings-editor-revision {
  flex-shrink: 0;
  font-size: var(--font-size-small);
}

.admin-settings-editor-precedence {
  max-inline-size: 65ch;
  padding: 0 var(--space-5) var(--space-5);
}

.admin-settings-editor-conflict {
  display: grid;
  gap: var(--space-3);
  margin: 0 var(--space-5) var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--critical);
  border-radius: var(--radius-card);
  background: var(--surface-1);
  color: var(--critical-text);
}

.admin-settings-editor-conflict p {
  margin: 0;
}

.admin-settings-editor-form {
  border-top: 1px solid var(--grid);
}

.admin-settings-editor-field-list {
  display: grid;
}

.admin-settings-editor-field {
  min-inline-size: 0;
  border-bottom: 1px solid var(--grid);
}

.admin-settings-editor-field--changed {
  background: var(--surface-1);
}

.admin-settings-editor-summary {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-4) var(--space-5);
}

.admin-settings-editor-summary-copy {
  min-inline-size: 0;
}

.admin-settings-editor-value,
.admin-settings-editor-source {
  overflow-wrap: anywhere;
}

.admin-settings-editor-value {
  margin: var(--space-1) 0 0;
}

.admin-settings-editor-value--cleared {
  color: var(--text-secondary);
  font-style: italic;
}

.admin-settings-editor-source {
  font-size: var(--font-size-small);
}

.admin-settings-editor-summary-actions,
.admin-settings-editor-action-buttons {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.admin-settings-editor-summary-actions {
  align-self: start;
}

.admin-settings-status {
  display: inline-block;
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  font-size: var(--font-size-small);
  font-weight: var(--weight-semibold);
}

.admin-settings-status--overridden,
.admin-settings-status--pending {
  border-color: var(--accent-b);
  color: var(--accent-b);
}

.admin-settings-status--pending {
  background: var(--panel);
}

.admin-settings-status--cleared {
  border-color: var(--warning);
  background: var(--surface-1);
  color: var(--text-primary);
}

.admin-settings-status--inherited {
  color: var(--text-secondary);
}

.admin-settings-editor-controls {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding: var(--space-4) var(--space-5) var(--space-5);
  border: 0;
  border-top: 1px solid var(--grid);
}

.admin-settings-editor-controls legend {
  padding: 0;
  font-weight: var(--weight-semibold);
}

.admin-settings-editor-fallback {
  margin: 0;
  font-size: var(--font-size-small);
}

.admin-settings-editor-mode {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
}

.admin-settings-editor-mode label,
.admin-settings-reset-field {
  display: flex;
  min-block-size: var(--control-min-size);
  align-items: center;
  gap: var(--space-2);
}

.admin-settings-editor-value-field {
  display: grid;
  gap: var(--space-2);
  max-inline-size: 44rem;
}

.admin-settings-editor-value-field > label {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.admin-settings-editor-value-field input,
.admin-settings-editor-value-field textarea {
  box-sizing: border-box;
  inline-size: 100%;
}

.admin-settings-editor-value-field textarea {
  resize: vertical;
}

.admin-settings-editor-value-field input[aria-invalid='true'],
.admin-settings-editor-value-field textarea[aria-invalid='true'] {
  border-color: var(--critical);
}

.admin-settings-editor-value-field > p[role='alert'],
.admin-settings-editor-error,
.admin-settings-reset-dirty {
  margin: 0;
  color: var(--critical-text);
}

.admin-settings-editor-error {
  padding: var(--space-4) var(--space-5) 0;
}

.admin-settings-editor-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3) var(--space-6);
  padding: var(--space-4) var(--space-5);
}

.admin-settings-editor-change-summary {
  margin: 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.admin-settings-reset {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-5);
  border-top: 1px solid var(--grid);
}

.admin-settings-reset-field label {
  display: grid;
  gap: var(--space-1);
}

.admin-settings-reset-field span {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.admin-settings-reset-backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
}

.admin-settings-reset-frame {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
}

.admin-settings-reset-panel {
  display: grid;
  gap: var(--space-4);
  width: 100%;
  max-width: 32rem;
  padding: var(--space-6);
  border-radius: var(--radius-modal);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
}

.admin-settings-reset-panel p,
.admin-settings-reset-panel ul {
  margin: 0;
  color: var(--text-secondary);
}

.admin-settings-reset-title {
  color: var(--text-primary);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
}

@container branding-editor (min-width: 38rem) {
  .admin-settings-editor-summary {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
  }
}

@media (max-width: 40rem) {
  .admin-settings-editor-heading,
  .admin-settings-editor-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .admin-settings-editor-action-buttons > * {
    flex: 1;
  }
}
</style>
