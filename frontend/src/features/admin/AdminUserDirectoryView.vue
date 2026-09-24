<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useAdminAccess } from '@/composables/useAdminAccess'

import { useAdminUserDirectory, type AdminUser } from './useAdminUserDirectory'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { state: accessState, canAccessAdmin, session } = useAdminAccess()
const searchInput = ref('')
const serverAccessError = ref<'forbidden' | 'passwordChangeRequired' | null>(null)
const principalId = computed(() => session.user?.id ?? null)
const canLoadDirectory = computed(() => canAccessAdmin.value && serverAccessError.value === null)
const directory = useAdminUserDirectory(principalId, canLoadDirectory, searchInput)
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

function retrySession(): void {
  void session.initialize()
}

function refetch(): void {
  void directory.query.refetch()
}

function loadMore(): void {
  void directory.query.fetchNextPage()
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
        <div class="admin-user-directory-table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">{{ t('admin.table.username') }}</th>
                <th scope="col">{{ t('admin.table.displayName') }}</th>
                <th scope="col">{{ t('admin.table.roles') }}</th>
                <th scope="col">{{ t('admin.table.active') }}</th>
                <th scope="col">{{ t('admin.table.passwordChange') }}</th>
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
              </tr>
            </tbody>
          </table>
        </div>

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
  flex: 1;
  width: 100%;
  max-width: 76rem;
  margin: 0 auto;
  padding: var(--space-8) var(--space-4);
}

.admin-user-directory-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
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
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}

.admin-user-directory-table-scroll table {
  width: 100%;
  min-width: 52rem;
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
  color: var(--critical);
}

.admin-user-directory-error,
.admin-user-directory-page-error {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
}

.admin-user-directory-error p,
.admin-user-directory-page-error p {
  margin: 0;
  color: var(--critical);
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
