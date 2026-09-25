<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, type components } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import { useAdminAccess } from '@/composables/useAdminAccess'

import AdminSettingsEditor from './AdminSettingsEditor.vue'
import { useAdminSettings, type AdminSettings } from './useAdminSettings'
import {
  useAdminSettingsMutations,
  type AdminSettingsMutationError,
  type AdminSettingsMutationResult,
} from './useAdminSettingsMutations'

type EditableBrandingValues = components['schemas']['BrandingEditableValues']
type EditableBrandingField = keyof EditableBrandingValues
type BrandingValue = string | number | string[] | null | undefined

const EDITABLE_BRANDING_FIELDS = [
  'institution_name',
  'institution_url',
  'contact_email',
  'privacy_notice_url',
  'editors',
  'published_since_year',
] as const satisfies readonly EditableBrandingField[]

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { state: accessState, canAccessAdmin, session } = useAdminAccess()
const principalId = computed(() => session.user?.id ?? null)
const serverAccessError = ref<'forbidden' | 'passwordChangeRequired' | null>(null)
const canLoadSettings = computed(() => canAccessAdmin.value && serverAccessError.value === null)
const settings = useAdminSettings(principalId, canLoadSettings)
const mutations = useAdminSettingsMutations(principalId, canLoadSettings)
const data = computed(() => settings.query.data.value ?? null)
const mutationError = ref<AdminSettingsMutationError | null>(null)
const hasConflict = ref(false)
const conflictLatest = ref<AdminSettings | null>(null)
const hasPublicRefreshFailure = ref(false)
const editorKey = ref(0)
const isSettingsUnavailable = computed(() => {
  const error = settings.query.error.value
  return error instanceof ApiError && error.status === 503 && error.code === 'settings_unavailable'
})

watch(
  accessState,
  (state) => {
    if (state === 'signedOut') {
      void router.replace({ name: 'login', query: { redirect: route.fullPath } })
    }
    if (state === 'passwordChangeRequired') {
      void router.replace({ name: 'changePassword', query: { redirect: route.fullPath } })
    }
  },
  { immediate: true },
)

watch(
  () => settings.query.error.value,
  (error) => {
    if (!(error instanceof ApiError)) return

    if (error.status === 403) {
      serverAccessError.value =
        error.code === 'password_change_required' ? 'passwordChangeRequired' : 'forbidden'
      clearPrivateMutationState()
      settings.clearPrivateData()
      void session.initialize()
    }
    if (error.status === 401) {
      clearPrivateMutationState()
      settings.clearPrivateData()
      void session.initialize()
    }
  },
)

watch([principalId, canLoadSettings], () => {
  clearPrivateMutationState()
  editorKey.value += 1
})

function retrySession(): void {
  void session.initialize()
}

function refetch(): void {
  void settings.query.refetch()
}

function clearPrivateMutationState(): void {
  mutationError.value = null
  hasConflict.value = false
  conflictLatest.value = null
  hasPublicRefreshFailure.value = false
}

async function retryPublicBrandingRefresh(): Promise<void> {
  hasPublicRefreshFailure.value = !(await mutations.refreshBranding())
}

async function handleMutation(result: AdminSettingsMutationResult): Promise<void> {
  switch (result.status) {
    case 'success':
      mutationError.value = null
      hasConflict.value = false
      conflictLatest.value = null
      hasPublicRefreshFailure.value = result.publicRefreshFailed
      editorKey.value += 1
      return
    case 'conflict':
      mutationError.value = null
      hasConflict.value = true
      conflictLatest.value = result.latest
      return
    case 'failure':
      mutationError.value = result.error
      if (
        result.error === 'authentication_required' ||
        result.error === 'password_change_required' ||
        result.error === 'forbidden'
      ) {
        serverAccessError.value =
          result.error === 'password_change_required' ? 'passwordChangeRequired' : 'forbidden'
        clearPrivateMutationState()
        settings.clearPrivateData()
        await session.initialize()
      }
      return
    case 'discarded':
      return
  }
}

async function saveSettings(command: components['schemas']['AdminSettingsUpdate']): Promise<void> {
  await handleMutation(await mutations.update(command))
}

async function resetSettings(command: components['schemas']['AdminSettingsReset']): Promise<void> {
  await handleMutation(await mutations.reset(command))
}

function discardDraft(): void {
  clearPrivateMutationState()
  editorKey.value += 1
}

function reconcileConflict(): void {
  hasConflict.value = false
  conflictLatest.value = null
  mutationError.value = null
}

function effectiveValue(settingsData: AdminSettings, field: EditableBrandingField): BrandingValue {
  return settingsData.branding[field]
}

function fallbackValue(settingsData: AdminSettings, field: EditableBrandingField): BrandingValue {
  return settingsData.branding_defaults[field]
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

function isOverridden(settingsData: AdminSettings, field: EditableBrandingField): boolean {
  return settingsData.overridden_fields.includes(field)
}

function isCleared(settingsData: AdminSettings, field: EditableBrandingField): boolean {
  if (!isOverridden(settingsData, field)) return false
  const value = effectiveValue(settingsData, field)
  return value === null || (Array.isArray(value) && value.length === 0)
}

function overrideStatus(settingsData: AdminSettings, field: EditableBrandingField): string {
  if (!isOverridden(settingsData, field)) return t('adminSettings.status.inherited')
  return isCleared(settingsData, field)
    ? t('adminSettings.status.cleared')
    : t('adminSettings.status.overridden')
}

function overrideStatusClass(settingsData: AdminSettings, field: EditableBrandingField): string {
  if (isCleared(settingsData, field)) return 'admin-settings-status--cleared'
  return isOverridden(settingsData, field)
    ? 'admin-settings-status--overridden'
    : 'admin-settings-status--inherited'
}

function formatValue(value: BrandingValue): string {
  if (Array.isArray(value)) {
    return value.length === 0 ? t('adminSettings.values.noEditors') : value.join(', ')
  }
  if (value === null || value === undefined) return t('adminSettings.values.notConfigured')
  return String(value)
}

function legalEntityValue(value: string | null | undefined): string {
  return value ?? t('adminSettings.values.notConfigured')
}

function legalEntityAddress(values: string[] | undefined): string {
  return values?.length ? values.join(', ') : t('adminSettings.values.notConfigured')
}
</script>

<template>
  <main class="admin-settings">
    <p v-if="accessState === 'loading'" role="status">{{ t('adminSettings.loadingAccess') }}</p>

    <div v-else-if="accessState === 'sessionError'" class="admin-settings-error">
      <p role="alert">{{ t('adminSettings.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('adminSettings.retry') }}</AppButton>
    </div>

    <div
      v-else-if="accessState === 'forbidden' || serverAccessError === 'forbidden'"
      class="admin-settings-error"
    >
      <h1>{{ t('adminSettings.title') }}</h1>
      <p role="alert">{{ t('adminSettings.forbidden') }}</p>
    </div>

    <div v-else-if="serverAccessError === 'passwordChangeRequired'" class="admin-settings-error">
      <h1>{{ t('adminSettings.title') }}</h1>
      <p role="alert">{{ t('adminSettings.passwordChangeRequired') }}</p>
    </div>

    <template v-else-if="canLoadSettings">
      <header class="admin-settings-heading">
        <div>
          <h1>{{ t('adminSettings.title') }}</h1>
          <p>{{ t('adminSettings.description') }}</p>
        </div>
        <AppButton
          type="button"
          variant="ghost"
          :disabled="settings.query.isFetching.value"
          @click="refetch"
        >
          {{ t('adminSettings.refetch') }}
        </AppButton>
      </header>

      <p class="admin-settings-read-only">{{ t('adminSettings.editingAvailable') }}</p>

      <p v-if="settings.query.isPending.value" role="status">{{ t('adminSettings.loading') }}</p>

      <div v-else-if="settings.query.isError.value" class="admin-settings-error">
        <p role="alert">
          {{
            isSettingsUnavailable
              ? t('adminSettings.settingsUnavailable')
              : t('adminSettings.loadError')
          }}
        </p>
        <AppButton type="button" @click="refetch">{{ t('adminSettings.retry') }}</AppButton>
      </div>

      <template v-else-if="data !== null">
        <section
          class="admin-settings-precedence"
          aria-labelledby="admin-settings-precedence-heading"
        >
          <h2 id="admin-settings-precedence-heading">{{ t('adminSettings.precedence.title') }}</h2>
          <p>{{ t('adminSettings.precedence.description') }}</p>
        </section>

        <section aria-labelledby="admin-settings-branding-heading">
          <div class="admin-settings-section-heading">
            <div>
              <h2 id="admin-settings-branding-heading">{{ t('adminSettings.branding.title') }}</h2>
              <p>{{ t('adminSettings.branding.description') }}</p>
            </div>
            <p class="admin-settings-revision">
              {{ t('adminSettings.revision', { revision: data.revision }) }}
            </p>
          </div>
          <AppScrollRegion
            class="admin-settings-table-scroll"
            :label="t('layout.tableRegion', { label: t('adminSettings.branding.title') })"
          >
            <table>
              <thead>
                <tr>
                  <th scope="col">{{ t('adminSettings.table.field') }}</th>
                  <th scope="col">{{ t('adminSettings.table.effectiveValue') }}</th>
                  <th scope="col">{{ t('adminSettings.table.deploymentFallback') }}</th>
                  <th scope="col">{{ t('adminSettings.table.overrideStatus') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="field in EDITABLE_BRANDING_FIELDS" :key="field">
                  <th scope="row">
                    {{ fieldLabel(field) }}
                    <code>{{ field }}</code>
                  </th>
                  <td :class="{ 'admin-settings-value--cleared': isCleared(data, field) }">
                    {{ formatValue(effectiveValue(data, field)) }}
                  </td>
                  <td>{{ formatValue(fallbackValue(data, field)) }}</td>
                  <td>
                    <span class="admin-settings-status" :class="overrideStatusClass(data, field)">
                      {{ overrideStatus(data, field) }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </AppScrollRegion>
        </section>

        <AdminSettingsEditor
          :key="editorKey"
          :settings="data"
          :is-submitting="mutations.isSubmitting.value"
          :mutation-error="mutationError"
          :has-conflict="hasConflict"
          :conflict-latest="conflictLatest"
          @save="saveSettings"
          @reset="resetSettings"
          @discard-draft="discardDraft"
          @reconcile-conflict="reconcileConflict"
        />

        <div v-if="hasPublicRefreshFailure" class="admin-settings-public-refresh-error">
          <p role="alert">{{ t('adminSettings.editing.publicRefreshFailed') }}</p>
          <AppButton type="button" variant="ghost" @click="retryPublicBrandingRefresh">
            {{ t('adminSettings.editing.retryPublicRefresh') }}
          </AppButton>
        </div>

        <section
          class="admin-settings-deployment"
          aria-labelledby="admin-settings-deployment-heading"
        >
          <h2 id="admin-settings-deployment-heading">{{ t('adminSettings.deployment.title') }}</h2>
          <p>{{ t('adminSettings.deployment.description') }}</p>

          <div class="admin-settings-deployment-grid">
            <section aria-labelledby="admin-settings-logo-heading">
              <h3 id="admin-settings-logo-heading">
                {{ t('adminSettings.deployment.logo.title') }}
              </h3>
              <p>{{ t('adminSettings.deployment.logo.description') }}</p>
              <p class="admin-settings-derived-value">
                {{ data.branding.logo_url ?? t('adminSettings.values.noLogo') }}
              </p>
            </section>

            <section aria-labelledby="admin-settings-initiatives-heading">
              <h3 id="admin-settings-initiatives-heading">
                {{ t('adminSettings.deployment.initiatives.title') }}
              </h3>
              <p>{{ t('adminSettings.deployment.initiatives.description') }}</p>
              <ul v-if="data.branding.initiatives?.length" class="admin-settings-list">
                <li v-for="initiative in data.branding.initiatives" :key="initiative.url">
                  <a :href="initiative.url">{{ initiative.name }}</a>
                </li>
              </ul>
              <p v-else>{{ t('adminSettings.values.noInitiatives') }}</p>
            </section>

            <section aria-labelledby="admin-settings-legal-entity-heading">
              <h3 id="admin-settings-legal-entity-heading">
                {{ t('adminSettings.deployment.legalEntity.title') }}
              </h3>
              <p>{{ t('adminSettings.deployment.legalEntity.description') }}</p>
              <dl v-if="data.branding.legal_entity" class="admin-settings-legal-entity">
                <div>
                  <dt>{{ t('adminSettings.deployment.legalEntity.name') }}</dt>
                  <dd>{{ data.branding.legal_entity.name }}</dd>
                </div>
                <div>
                  <dt>{{ t('adminSettings.deployment.legalEntity.legalForm') }}</dt>
                  <dd>{{ legalEntityValue(data.branding.legal_entity.legal_form) }}</dd>
                </div>
                <div>
                  <dt>{{ t('adminSettings.deployment.legalEntity.address') }}</dt>
                  <dd>{{ legalEntityAddress(data.branding.legal_entity.address_lines) }}</dd>
                </div>
                <div>
                  <dt>{{ t('adminSettings.deployment.legalEntity.telephone') }}</dt>
                  <dd>{{ legalEntityValue(data.branding.legal_entity.telephone) }}</dd>
                </div>
                <div>
                  <dt>{{ t('adminSettings.deployment.legalEntity.representative') }}</dt>
                  <dd>{{ legalEntityValue(data.branding.legal_entity.representative) }}</dd>
                </div>
                <div>
                  <dt>{{ t('adminSettings.deployment.legalEntity.vatId') }}</dt>
                  <dd>{{ legalEntityValue(data.branding.legal_entity.vat_id) }}</dd>
                </div>
              </dl>
              <p v-else>{{ t('adminSettings.values.noLegalEntity') }}</p>
            </section>
          </div>
        </section>
      </template>
    </template>
  </main>
</template>

<style scoped>
.admin-settings {
  flex: 1;
  width: 100%;
  max-width: 76rem;
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
}

.admin-settings-heading,
.admin-settings-section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
}

.admin-settings-heading {
  margin-bottom: var(--space-5);
}

.admin-settings h1,
.admin-settings h2,
.admin-settings h3 {
  margin: 0;
  color: var(--text-primary);
  font-weight: var(--weight-semibold);
}

.admin-settings h1 {
  font-size: var(--font-size-page);
}

.admin-settings h2 {
  font-size: var(--font-size-title);
}

.admin-settings h3 {
  font-size: var(--font-size-body-strong);
}

.admin-settings-heading p,
.admin-settings-section-heading p,
.admin-settings-precedence p,
.admin-settings-deployment > p,
.admin-settings-deployment-grid section > p {
  margin: var(--space-2) 0 0;
  color: var(--text-secondary);
}

.admin-settings-read-only,
.admin-settings-precedence {
  margin: 0 0 var(--space-6);
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--surface-1);
  color: var(--text-secondary);
}

.admin-settings-precedence {
  display: grid;
  gap: var(--space-2);
}

.admin-settings-precedence p {
  margin: 0;
}

.admin-settings-section-heading {
  margin-bottom: var(--space-4);
}

.admin-settings-revision {
  flex-shrink: 0;
  font-size: var(--font-size-small);
}

.admin-settings-table-scroll {
  margin-bottom: var(--space-8);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.admin-settings table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}

.admin-settings th,
.admin-settings td {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--grid);
  vertical-align: top;
}

.admin-settings thead th {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  font-weight: var(--weight-semibold);
}

.admin-settings tbody tr:last-child th,
.admin-settings tbody tr:last-child td {
  border-bottom: 0;
}

.admin-settings tbody th {
  min-width: 13rem;
  color: var(--text-primary);
  font-weight: var(--weight-semibold);
}

.admin-settings code {
  display: block;
  margin-top: var(--space-1);
  color: var(--muted);
  font-size: var(--font-size-caption);
  overflow-wrap: anywhere;
}

.admin-settings-value--cleared {
  color: var(--text-secondary);
  font-style: italic;
}

.admin-settings-status {
  display: inline-block;
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  font-size: var(--font-size-small);
  font-weight: var(--weight-semibold);
}

.admin-settings-status--overridden {
  border-color: var(--accent-b);
  color: var(--accent-b);
}

.admin-settings-status--cleared {
  border-color: var(--warning);
  color: var(--text-primary);
  background: var(--surface-1);
}

.admin-settings-status--inherited {
  color: var(--text-secondary);
}

.admin-settings-deployment {
  display: grid;
  gap: var(--space-2);
}

.admin-settings-deployment-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
  margin-top: var(--space-3);
}

.admin-settings-deployment-grid section {
  min-width: 0;
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.admin-settings-derived-value,
.admin-settings-list,
.admin-settings-legal-entity {
  margin: var(--space-3) 0 0;
}

.admin-settings-derived-value {
  overflow-wrap: anywhere;
}

.admin-settings-list {
  padding-left: var(--space-4);
}

.admin-settings-list a {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.admin-settings-legal-entity {
  display: grid;
  gap: var(--space-3);
}

.admin-settings-legal-entity div {
  display: grid;
  gap: var(--space-1);
}

.admin-settings-legal-entity dt {
  color: var(--muted);
  font-size: var(--font-size-caption);
  font-weight: var(--weight-semibold);
}

.admin-settings-legal-entity dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.admin-settings-error {
  display: grid;
  justify-items: start;
  gap: var(--space-4);
}

.admin-settings-error p {
  margin: 0;
  color: var(--critical-text);
}

.admin-settings-public-refresh-error {
  display: grid;
  justify-items: start;
  gap: var(--space-3);
  margin-top: var(--space-4);
  color: var(--critical-text);
}

.admin-settings-public-refresh-error p {
  margin: 0;
}

@media (max-width: 56rem) {
  .admin-settings-deployment-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 40rem) {
  .admin-settings-heading,
  .admin-settings-section-heading {
    flex-direction: column;
  }

  .admin-settings th,
  .admin-settings td {
    min-width: 10rem;
  }
}
</style>
