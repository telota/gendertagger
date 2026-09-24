<script setup lang="ts">
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { components } from '@/api'
import AppButton from '@/components/base/AppButton.vue'

import type { AdminSettings } from './useAdminSettings'
import type { AdminSettingsMutationError } from './useAdminSettingsMutations'

type EditableBrandingValues = components['schemas']['BrandingEditableValues']
type EditableBrandingField = keyof EditableBrandingValues
type FieldMode = 'unchanged' | 'set' | 'clear'

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

const hasChanges = computed(() =>
  EDITABLE_BRANDING_FIELDS.some((field) => modes.value[field] !== 'unchanged'),
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
    <h2 id="admin-settings-editor-heading">{{ t('adminSettings.editing.title') }}</h2>
    <p>{{ t('adminSettings.editing.description') }}</p>

    <div v-if="hasConflict" class="admin-settings-editor-conflict" role="alert">
      <p v-if="conflictLatest">
        {{
          t('adminSettings.editing.conflict.latestLoaded', { revision: conflictLatest.revision })
        }}
      </p>
      <p v-else>{{ t('adminSettings.editing.conflict.latestUnavailable') }}</p>
      <div v-if="conflictLatest" class="admin-settings-editor-actions">
        <AppButton type="button" @click="reconcileConflict">
          {{ t('adminSettings.editing.conflict.reconcile') }}
        </AppButton>
        <AppButton type="button" variant="ghost" @click="discardDraft">
          {{ t('adminSettings.editing.discard') }}
        </AppButton>
      </div>
    </div>

    <form novalidate class="admin-settings-editor-form" @submit.prevent="submit">
      <fieldset
        v-for="field in EDITABLE_BRANDING_FIELDS"
        :key="field"
        class="admin-settings-editor-field"
      >
        <legend>{{ fieldLabel(field) }}</legend>
        <div class="admin-settings-editor-mode">
          <label>
            <input v-model="modes[field]" type="radio" :name="`${field}-mode`" value="unchanged" />
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
        <p class="admin-settings-editor-fallback">
          {{ t('adminSettings.editing.fallback', { value: fallbackValue(field) }) }}
        </p>
        <label :for="`admin-settings-${field}`">{{ t('adminSettings.editing.value') }}</label>
        <textarea
          v-if="field === 'editors'"
          :id="`admin-settings-${field}`"
          v-model="values[field]"
          :name="field"
          :readonly="modes[field] !== 'set'"
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
          :readonly="modes[field] !== 'set'"
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
      </fieldset>

      <p v-if="errorMessage(mutationError)" role="alert" class="admin-settings-editor-error">
        {{ errorMessage(mutationError) }}
      </p>
      <div class="admin-settings-editor-actions">
        <AppButton type="submit" :disabled="!hasChanges || isSubmitting || hasConflict">
          {{
            isSubmitting ? t('adminSettings.editing.submitting') : t('adminSettings.editing.save')
          }}
        </AppButton>
        <AppButton type="button" variant="ghost" :disabled="isSubmitting" @click="discardDraft">
          {{ t('adminSettings.editing.discard') }}
        </AppButton>
      </div>
    </form>

    <section class="admin-settings-reset" aria-labelledby="admin-settings-reset-heading">
      <h3 id="admin-settings-reset-heading">{{ t('adminSettings.reset.title') }}</h3>
      <p>{{ t('adminSettings.reset.description') }}</p>
      <p v-if="hasChanges" class="admin-settings-reset-dirty">
        {{ t('adminSettings.reset.unsavedChanges') }}
      </p>
      <template v-else-if="settings.overridden_fields.length">
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
      <p v-else>{{ t('adminSettings.reset.none') }}</p>
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
          <div class="admin-settings-editor-actions">
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
.admin-settings-editor,
.admin-settings-reset {
  margin-top: var(--space-8);
  padding: var(--space-5);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.admin-settings-editor h2,
.admin-settings-editor h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.admin-settings-editor > p,
.admin-settings-reset > p,
.admin-settings-editor-fallback,
.admin-settings-editor-hint {
  margin: var(--space-2) 0 0;
  color: var(--text-secondary);
}

.admin-settings-editor-form {
  display: grid;
  gap: var(--space-5);
  margin-top: var(--space-5);
}

.admin-settings-editor-field {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  border: 0;
}

.admin-settings-editor-field legend,
.admin-settings-editor-field > label {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.admin-settings-editor-field legend {
  color: var(--text-primary);
  font-weight: var(--weight-semibold);
}

.admin-settings-editor-mode,
.admin-settings-editor-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
}

.admin-settings-editor-mode label,
.admin-settings-reset-field {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
}

.admin-settings-editor-field input,
.admin-settings-editor-field textarea {
  box-sizing: border-box;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  padding: var(--space-2) var(--space-3);
}

.admin-settings-editor-field textarea {
  resize: vertical;
}

.admin-settings-editor-field input[readonly],
.admin-settings-editor-field textarea[readonly] {
  background: var(--surface-1);
  color: var(--text-secondary);
}

.admin-settings-editor-field input[aria-invalid='true'],
.admin-settings-editor-field textarea[aria-invalid='true'] {
  border-color: var(--critical);
}

.admin-settings-editor-field > p[role='alert'],
.admin-settings-editor-error,
.admin-settings-editor-conflict,
.admin-settings-reset-dirty {
  margin: 0;
  color: var(--critical);
}

.admin-settings-editor-conflict {
  display: grid;
  gap: var(--space-3);
  margin-top: var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--critical);
  border-radius: var(--radius-card);
  background: var(--surface-1);
}

.admin-settings-editor-conflict p {
  margin: 0;
}

.admin-settings-reset {
  display: grid;
  gap: var(--space-3);
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
</style>
