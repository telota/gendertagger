<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, type components } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import { useAdminAccess } from '@/composables/useAdminAccess'

import AdminSettingsEditor from './AdminSettingsEditor.vue'
import { useAdminSettings, type AdminSettings } from './useAdminSettings'
import {
  useAdminSettingsMutations,
  type AdminSettingsMutationError,
  type AdminSettingsMutationResult,
} from './useAdminSettingsMutations'

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

function legalEntityValue(value: string | null | undefined): string {
  return value ?? t('adminSettings.values.notConfigured')
}

function legalEntityAddress(values: string[] | undefined): string {
  return values?.length ? values.join(', ') : t('adminSettings.values.notConfigured')
}
</script>

<template>
  <main class="admin-settings app-page-frame">
    <header class="admin-settings-heading app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="app-page-heading__title">{{ t('adminSettings.title') }}</h1>
        <p v-if="canLoadSettings" class="app-page-heading__description">
          {{ t('adminSettings.description') }}
        </p>
      </div>
      <div v-if="canLoadSettings" class="app-page-heading__actions">
        <AppButton
          type="button"
          variant="ghost"
          :disabled="settings.query.isFetching.value"
          @click="refetch"
        >
          {{ t('adminSettings.refetch') }}
        </AppButton>
      </div>
    </header>

    <AppFeedback
      v-if="accessState === 'loading'"
      class="admin-settings-state app-card"
      announcement="polite"
    >
      {{ t('adminSettings.loadingAccess') }}
    </AppFeedback>

    <AppFeedback
      v-else-if="accessState === 'sessionError'"
      class="admin-settings-error app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('adminSettings.sessionLoadError') }}
      <template #actions>
        <AppButton type="button" @click="retrySession">{{ t('adminSettings.retry') }}</AppButton>
      </template>
    </AppFeedback>

    <AppFeedback
      v-else-if="accessState === 'forbidden' || serverAccessError === 'forbidden'"
      class="admin-settings-error app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('adminSettings.forbidden') }}
    </AppFeedback>

    <AppFeedback
      v-else-if="serverAccessError === 'passwordChangeRequired'"
      class="admin-settings-error app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('adminSettings.passwordChangeRequired') }}
    </AppFeedback>

    <template v-else-if="canLoadSettings">
      <AppFeedback
        v-if="settings.query.isPending.value"
        class="admin-settings-state app-card"
        announcement="polite"
      >
        {{ t('adminSettings.loading') }}
      </AppFeedback>

      <AppFeedback
        v-else-if="settings.query.isError.value"
        class="admin-settings-error app-card"
        announcement="assertive"
        tone="critical"
      >
        {{
          isSettingsUnavailable
            ? t('adminSettings.settingsUnavailable')
            : t('adminSettings.loadError')
        }}
        <template #actions>
          <AppButton type="button" @click="refetch">{{ t('adminSettings.retry') }}</AppButton>
        </template>
      </AppFeedback>

      <template v-else-if="data !== null">
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

        <AppFeedback
          v-if="hasPublicRefreshFailure"
          class="admin-settings-public-refresh-error app-card"
          announcement="assertive"
          tone="critical"
        >
          {{ t('adminSettings.editing.publicRefreshFailed') }}
          <template #actions>
            <AppButton type="button" variant="ghost" @click="retryPublicBrandingRefresh">
              {{ t('adminSettings.editing.retryPublicRefresh') }}
            </AppButton>
          </template>
        </AppFeedback>

        <section
          class="admin-settings-deployment"
          aria-labelledby="admin-settings-deployment-heading"
        >
          <div class="admin-settings-section-heading">
            <div>
              <h2 id="admin-settings-deployment-heading">
                {{ t('adminSettings.deployment.title') }}
              </h2>
              <p>{{ t('adminSettings.deployment.description') }}</p>
            </div>
          </div>

          <div class="admin-settings-deployment-card app-card app-card--sectioned">
            <section aria-labelledby="admin-settings-logo-heading">
              <div>
                <h3 id="admin-settings-logo-heading">
                  {{ t('adminSettings.deployment.logo.title') }}
                </h3>
                <p>{{ t('adminSettings.deployment.logo.description') }}</p>
              </div>
              <p class="admin-settings-derived-value">
                {{ data.branding.logo_url ?? t('adminSettings.values.noLogo') }}
              </p>
            </section>

            <section aria-labelledby="admin-settings-initiatives-heading">
              <div>
                <h3 id="admin-settings-initiatives-heading">
                  {{ t('adminSettings.deployment.initiatives.title') }}
                </h3>
                <p>{{ t('adminSettings.deployment.initiatives.description') }}</p>
              </div>
              <ul v-if="data.branding.initiatives?.length" class="admin-settings-list">
                <li v-for="initiative in data.branding.initiatives" :key="initiative.url">
                  <a :href="initiative.url">{{ initiative.name }}</a>
                </li>
              </ul>
              <p v-else class="admin-settings-derived-value">
                {{ t('adminSettings.values.noInitiatives') }}
              </p>
            </section>

            <section aria-labelledby="admin-settings-legal-entity-heading">
              <div>
                <h3 id="admin-settings-legal-entity-heading">
                  {{ t('adminSettings.deployment.legalEntity.title') }}
                </h3>
                <p>{{ t('adminSettings.deployment.legalEntity.description') }}</p>
              </div>
              <dl
                v-if="data.branding.legal_entity"
                class="admin-settings-legal-entity app-fact-list"
              >
                <div class="app-fact-list__item">
                  <dt>{{ t('adminSettings.deployment.legalEntity.name') }}</dt>
                  <dd>{{ data.branding.legal_entity.name }}</dd>
                </div>
                <div class="app-fact-list__item">
                  <dt>{{ t('adminSettings.deployment.legalEntity.legalForm') }}</dt>
                  <dd>{{ legalEntityValue(data.branding.legal_entity.legal_form) }}</dd>
                </div>
                <div class="app-fact-list__item">
                  <dt>{{ t('adminSettings.deployment.legalEntity.address') }}</dt>
                  <dd>{{ legalEntityAddress(data.branding.legal_entity.address_lines) }}</dd>
                </div>
                <div class="app-fact-list__item">
                  <dt>{{ t('adminSettings.deployment.legalEntity.telephone') }}</dt>
                  <dd>{{ legalEntityValue(data.branding.legal_entity.telephone) }}</dd>
                </div>
                <div class="app-fact-list__item">
                  <dt>{{ t('adminSettings.deployment.legalEntity.representative') }}</dt>
                  <dd>{{ legalEntityValue(data.branding.legal_entity.representative) }}</dd>
                </div>
                <div class="app-fact-list__item">
                  <dt>{{ t('adminSettings.deployment.legalEntity.vatId') }}</dt>
                  <dd>{{ legalEntityValue(data.branding.legal_entity.vat_id) }}</dd>
                </div>
              </dl>
              <p v-else class="admin-settings-derived-value">
                {{ t('adminSettings.values.noLegalEntity') }}
              </p>
            </section>
          </div>
        </section>
      </template>
    </template>
  </main>
</template>

<style scoped>
.admin-settings {
  container: admin-settings / inline-size;
}

.admin-settings-section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
}

.admin-settings h2,
.admin-settings h3 {
  margin: 0;
  color: var(--text-primary);
  font-weight: var(--weight-semibold);
}

.admin-settings h2 {
  font-size: var(--font-size-title);
}

.admin-settings h3 {
  font-size: var(--font-size-body-strong);
}

.admin-settings-section-heading p,
.admin-settings-deployment-card section > div > p {
  max-inline-size: 65ch;
  margin: var(--space-2) 0 0;
  color: var(--text-secondary);
}

.admin-settings-editor {
  margin-block-end: var(--space-8);
}

.admin-settings-section-heading {
  margin-block-end: var(--space-4);
}

.admin-settings-deployment-card > section {
  display: grid;
  gap: var(--space-4);
  min-inline-size: 0;
  padding: var(--space-4);
}

.admin-settings-deployment-card > section + section {
  border-block-start: 1px solid var(--grid);
}

.admin-settings-derived-value,
.admin-settings-list,
.admin-settings-legal-entity {
  margin: 0;
}

.admin-settings-derived-value {
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}

.admin-settings-list {
  padding-inline-start: var(--space-4);
}

.admin-settings-list a {
  color: var(--accent);
  text-underline-offset: 0.2em;
}

.admin-settings-legal-entity dt {
  color: var(--muted);
  font-size: var(--font-size-caption);
  font-weight: var(--weight-semibold);
}

.admin-settings-public-refresh-error {
  margin-block-end: var(--space-8);
}

@container admin-settings (min-width: 40rem) {
  .admin-settings-deployment-card > section {
    grid-template-columns: minmax(0, 1fr) minmax(16rem, 1fr);
    align-items: start;
  }
}

@media (max-width: 40rem) {
  .admin-settings-section-heading {
    flex-direction: column;
  }
}
</style>
