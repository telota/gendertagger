<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, type components } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useAdminAccess } from '@/composables/useAdminAccess'

import AdminUserCreationForm from './AdminUserCreationForm.vue'
import AdminUserEditForm from './AdminUserEditForm.vue'
import AdminUserSecurityActions from './AdminUserSecurityActions.vue'
import { useAdminUserDirectory, type AdminUser } from './useAdminUserDirectory'
import { useAdminUserMutations } from './useAdminUserMutations'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { state: accessState, canAccessAdmin, session } = useAdminAccess()
const searchInput = ref('')
const serverAccessError = ref<'forbidden' | 'passwordChangeRequired' | null>(null)
const principalId = computed(() => session.user?.id ?? null)
const canLoadDirectory = computed(() => canAccessAdmin.value && serverAccessError.value === null)
const directory = useAdminUserDirectory(principalId, canLoadDirectory, searchInput)
const mutations = useAdminUserMutations(principalId, canLoadDirectory)
const editingAccount = ref<AdminUser | null>(null)
const accounts = computed(
  () => directory.query.data.value?.pages.flatMap((page) => page.items) ?? [],
)
const hasAccounts = computed(() => accounts.value.length > 0)
const hasSearch = computed(() => directory.search.value.trim() !== '')

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

watch(accessState, (state) => {
  if (state !== 'eligible') editingAccount.value = null
})

watch(
  () => directory.query.error.value,
  (error) => {
    if (!(error instanceof ApiError) || error.status !== 403) return

    serverAccessError.value =
      error.code === 'password_change_required' ? 'passwordChangeRequired' : 'forbidden'
    directory.clearPrivateData()
    void session.initialize()
  },
)

watch(
  [mutations.createError, mutations.updateError, mutations.securityError],
  ([createError, updateError, securityError]) => {
    const error = createError ?? updateError ?? securityError
    if (!mutations.isAdminAccessError(error)) return

    serverAccessError.value =
      error === 'password_change_required' ? 'passwordChangeRequired' : 'forbidden'
    editingAccount.value = null
    mutations.clearPrivateState()
    void session.initialize()
    directory.clearPrivateData()
  },
)

function retrySession(): void {
  void session.initialize()
}

function refetch(): void {
  void directory.query.refetch()
}

function loadMore(): void {
  void directory.query.fetchNextPage()
}

async function createAccount(command: components['schemas']['AdminUserCreate']): Promise<void> {
  await mutations.create(command)
}

function startEditing(account: AdminUser): void {
  editingAccount.value = account
}

async function updateAccount(command: components['schemas']['AdminUserUpdate']): Promise<void> {
  const account = editingAccount.value
  if (account === null) return

  const updated = await mutations.update(account.id, command)
  if (updated === null) return

  editingAccount.value = null
  if (updated.id === principalId.value) await session.initialize()
}

async function resetAccountPassword(account: AdminUser): Promise<void> {
  await mutations.resetPassword(account)
}

async function revokeAccountSessions(account: AdminUser): Promise<void> {
  const isCurrentAccount = account.id === principalId.value
  const succeeded = await mutations.revokeSessions(account)
  if (!succeeded || !isCurrentAccount) return

  // The server has already revoked this browser session. Clear only local/private state and route to
  // sign-in; a logout request or an administrative refetch would be redundant and cannot authenticate.
  directory.clearPrivateData(account.id)
  mutations.clearPrivateState()
  session.forgetSession()
  await router.replace({ name: 'login' })
}

function roleLabel(role: AdminUser['roles'][number]): string {
  switch (role) {
    case 'admin':
      return t('admin.roles.admin')
    case 'operator':
      return t('admin.roles.operator')
  }
}

function rolesLabel(account: AdminUser): string {
  return account.roles.length === 0
    ? t('admin.roles.none')
    : account.roles.map((role) => roleLabel(role)).join(', ')
}
</script>

<template>
  <main class="admin-user-directory">
    <p v-if="accessState === 'loading'" role="status">{{ t('admin.loadingAccess') }}</p>

    <div v-else-if="accessState === 'sessionError'" class="admin-user-directory-error">
      <p role="alert">{{ t('admin.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('admin.retry') }}</AppButton>
    </div>

    <div
      v-else-if="accessState === 'forbidden' || serverAccessError === 'forbidden'"
      class="admin-user-directory-error"
    >
      <h1>{{ t('admin.title') }}</h1>
      <p role="alert">{{ t('admin.forbidden') }}</p>
    </div>

    <div
      v-else-if="serverAccessError === 'passwordChangeRequired'"
      class="admin-user-directory-error"
    >
      <h1>{{ t('admin.title') }}</h1>
      <p role="alert">{{ t('admin.passwordChangeRequired') }}</p>
    </div>

    <template v-else-if="canLoadDirectory">
      <header class="admin-user-directory-heading">
        <div>
          <h1>{{ t('admin.title') }}</h1>
          <p>{{ t('admin.description') }}</p>
        </div>
        <AppButton
          type="button"
          variant="ghost"
          :disabled="directory.query.isFetching.value"
          @click="refetch"
        >
          {{ t('admin.refetch') }}
        </AppButton>
      </header>

      <AdminUserCreationForm
        :key="principalId ?? 'anonymous'"
        :is-submitting="mutations.isCreating.value"
        :error="mutations.createError.value"
        :temporary-password="mutations.temporaryPassword.value"
        @create="createAccount"
        @dismiss-temporary-password="mutations.clearTemporaryPassword"
      />

      <AppTextField
        id="admin-user-search"
        v-model="searchInput"
        class="admin-user-directory-search"
        :label="t('admin.search.label')"
        :name="'query'"
        :autocomplete="'off'"
      />

      <p v-if="directory.query.isPending.value" role="status">{{ t('admin.loading') }}</p>

      <div
        v-else-if="directory.query.isError.value && !hasAccounts"
        class="admin-user-directory-error"
      >
        <p role="alert">{{ t('admin.loadError') }}</p>
        <AppButton type="button" @click="refetch">{{ t('admin.retry') }}</AppButton>
      </div>

      <p v-else-if="!hasAccounts" class="admin-user-directory-empty">
        {{ hasSearch ? t('admin.search.empty') : t('admin.empty') }}
      </p>

      <template v-else>
        <AppScrollRegion
          class="admin-user-directory-table-scroll"
          :label="t('layout.tableRegion', { label: t('admin.title') })"
        >
          <table>
            <thead>
              <tr>
                <th scope="col">{{ t('admin.table.username') }}</th>
                <th scope="col">{{ t('admin.table.displayName') }}</th>
                <th scope="col">{{ t('admin.table.roles') }}</th>
                <th scope="col">{{ t('admin.table.active') }}</th>
                <th scope="col">{{ t('admin.table.passwordChange') }}</th>
                <th scope="col">{{ t('admin.table.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="account in accounts" :key="account.id">
                <th scope="row" class="admin-user-directory-username">
                  {{ account.username }}
                  <span v-if="account.id === principalId" class="admin-user-directory-current">
                    {{ t('admin.currentAccount') }}
                  </span>
                </th>
                <td>{{ account.display_name }}</td>
                <td>{{ rolesLabel(account) }}</td>
                <td>
                  <span
                    class="admin-user-directory-state"
                    :class="
                      account.is_active
                        ? 'admin-user-directory-state--active'
                        : 'admin-user-directory-state--inactive'
                    "
                  >
                    {{ account.is_active ? t('admin.states.active') : t('admin.states.inactive') }}
                  </span>
                </td>
                <td>
                  <span
                    class="admin-user-directory-state"
                    :class="
                      account.must_change_password
                        ? 'admin-user-directory-state--required'
                        : 'admin-user-directory-state--current'
                    "
                  >
                    {{
                      account.must_change_password
                        ? t('admin.states.passwordChangeRequired')
                        : t('admin.states.passwordCurrent')
                    }}
                  </span>
                </td>
                <td>
                  <div class="admin-user-directory-actions">
                    <AppButton type="button" variant="text" @click="startEditing(account)">
                      {{ t('admin.editing.open') }}
                    </AppButton>
                    <AdminUserSecurityActions
                      v-if="principalId !== null"
                      :account="account"
                      :actor-user-id="principalId"
                      :is-submitting="mutations.isPerformingSecurityAction.value"
                      :error="mutations.securityError.value"
                      :error-target-user-id="mutations.securityTargetUserId.value"
                      :reset-disclosure="mutations.resetDisclosure.value"
                      :reset-directory-refresh-failed="mutations.resetDirectoryRefreshFailed.value"
                      @reset-password="resetAccountPassword"
                      @revoke-sessions="revokeAccountSessions"
                      @dismiss-reset-disclosure="mutations.clearResetDisclosure"
                    />
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </AppScrollRegion>

        <AdminUserEditForm
          v-if="editingAccount !== null && principalId !== null"
          :key="`${principalId}-${editingAccount.id}`"
          :account="editingAccount"
          :actor-user-id="principalId"
          :is-submitting="mutations.isUpdating.value"
          :error="mutations.updateError.value"
          @cancel="editingAccount = null"
          @save="updateAccount"
        />

        <div
          v-if="directory.query.isFetchNextPageError.value"
          class="admin-user-directory-page-error"
        >
          <p role="alert">{{ t('admin.paginationError') }}</p>
          <AppButton type="button" variant="ghost" @click="loadMore">{{
            t('admin.retry')
          }}</AppButton>
        </div>

        <AppButton
          v-else-if="directory.query.hasNextPage.value"
          class="admin-user-directory-load-more"
          type="button"
          variant="ghost"
          :disabled="directory.query.isFetchingNextPage.value"
          @click="loadMore"
        >
          {{ directory.query.isFetchingNextPage.value ? t('admin.loading') : t('admin.loadMore') }}
        </AppButton>
      </template>
    </template>
  </main>
</template>

<style scoped>
.admin-user-directory {
  min-width: 0;
  overflow-wrap: anywhere;
  flex: 1;
  width: 100%;
  max-width: 76rem;
  margin: 0 auto;
  padding: var(--space-8) var(--page-gutter);
}

.admin-user-directory-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.admin-user-directory-actions {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
}
.admin-user-directory-heading h1 {
  margin: 0 0 var(--space-2);
  font-size: var(--font-size-page);
  font-weight: var(--weight-semibold);
  line-height: var(--line-height-page);
}

.admin-user-directory-heading p,
.admin-user-directory-empty {
  margin: 0;
  color: var(--text-secondary);
}

.admin-user-directory-search {
  max-width: 28rem;
  margin-bottom: var(--space-6);
}

.admin-user-directory-table-scroll {
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.admin-user-directory-table-scroll table {
  min-width: 60rem;
  border-collapse: collapse;
  font-size: var(--font-size-body);
}

.admin-user-directory-table-scroll th,
.admin-user-directory-table-scroll td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--grid);
  text-align: left;
  vertical-align: top;
}

.admin-user-directory-table-scroll thead th {
  color: var(--text-secondary);
  font-size: var(--font-size-caption);
  font-weight: var(--weight-semibold);
}

.admin-user-directory-table-scroll tbody tr:last-child th,
.admin-user-directory-table-scroll tbody tr:last-child td {
  border-bottom: 0;
}

.admin-user-directory-username {
  font-weight: var(--weight-semibold);
}

.admin-user-directory-current,
.admin-user-directory-state {
  display: inline-block;
  margin-top: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  font-size: var(--font-size-caption);
  font-weight: var(--weight-semibold);
}

.admin-user-directory-current {
  margin-left: var(--space-2);
  color: var(--accent);
}

.admin-user-directory-state--active,
.admin-user-directory-state--current {
  color: var(--good);
}

.admin-user-directory-state--inactive,
.admin-user-directory-state--required {
  color: var(--critical-text);
}

.admin-user-directory-error,
.admin-user-directory-page-error {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--space-4);
}

.admin-user-directory-error p,
.admin-user-directory-page-error p {
  margin: 0;
  color: var(--critical-text);
}

.admin-user-directory-page-error {
  margin-top: var(--space-4);
}

.admin-user-directory-load-more {
  margin-top: var(--space-4);
}

@media (max-width: 40rem) {
  .admin-user-directory-heading {
    flex-direction: column;
  }
}
</style>
