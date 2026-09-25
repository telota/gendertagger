<script setup lang="ts">
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import AppButton from '@/components/base/AppButton.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useAdminAccess } from '@/composables/useAdminAccess'
import { useDraftRegistration } from '@/composables/useDraftNavigation'

import { useAdminUserDirectory, type AdminUser } from './useAdminUserDirectory'
import {
  useAdminTeamMutations,
  type TeamMutationError,
  type TeamMutationOperation,
} from './useAdminTeamMutations'
import { useAdminTeams, type TeamMember, type TeamSummary } from './useAdminTeams'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { state: accessState, canAccessAdmin, session } = useAdminAccess()
const principalId = computed(() => session.user?.id ?? null)
const serverAccessError = ref<'forbidden' | 'passwordChangeRequired' | null>(null)
const canLoadTeams = computed(() => canAccessAdmin.value && serverAccessError.value === null)
const teamSearchInput = ref('')
const rosterSearchInput = ref('')
const accountSearchInput = ref('')
const selectedTeam = ref<TeamSummary | null>(null)
const selectedTeamId = computed(() => selectedTeam.value?.id ?? null)
const canLoadAccounts = computed(() => canLoadTeams.value && selectedTeamId.value !== null)
const createSlug = ref('')
const createDisplayName = ref('')
const renameDisplayName = ref('')
const confirmation = ref<'deleteTeam' | 'removeMember' | null>(null)
const memberToRemove = ref<TeamMember | null>(null)

const teams = useAdminTeams(
  principalId,
  canLoadTeams,
  teamSearchInput,
  selectedTeamId,
  rosterSearchInput,
)
const accountDirectory = useAdminUserDirectory(principalId, canLoadAccounts, accountSearchInput)
const mutations = useAdminTeamMutations(principalId, canLoadTeams, selectedTeamId)
const teamRows = computed(
  () => teams.teamsQuery.data.value?.pages.flatMap((page) => page.items) ?? [],
)
const rosterRows = computed(
  () => teams.rosterQuery.data.value?.pages.flatMap((page) => page.items) ?? [],
)
const accountRows = computed(
  () => accountDirectory.query.data.value?.pages.flatMap((page) => page.items) ?? [],
)
const hasTeams = computed(() => teamRows.value.length > 0)
const hasRosterMembers = computed(() => rosterRows.value.length > 0)
const hasAccounts = computed(() => accountRows.value.length > 0)
const hasTeamSearch = computed(() => teams.teamSearch.value.trim() !== '')
const hasRosterSearch = computed(() => teams.rosterSearch.value.trim() !== '')
const hasAccountSearch = computed(() => accountDirectory.search.value.trim() !== '')
const activeTeam = computed(() => selectedTeam.value)
const isDeletingTeam = computed(() => mutations.isMutating.value)

useDraftRegistration(
  () =>
    createSlug.value !== '' ||
    createDisplayName.value !== '' ||
    (activeTeam.value !== null && renameDisplayName.value !== activeTeam.value.display_name),
  () => {
    createSlug.value = ''
    createDisplayName.value = ''
    renameDisplayName.value = ''
    selectedTeam.value = null
    confirmation.value = null
    memberToRemove.value = null
  },
)

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

watch(teams.teamSearch, (nextSearch, previousSearch) => {
  if (nextSearch !== previousSearch) selectTeam(null)
})

watch(
  [
    () => teams.teamsQuery.error.value,
    () => teams.rosterQuery.error.value,
    () => accountDirectory.query.error.value,
  ],
  ([teamError, rosterError, accountError]) => {
    const error = teamError ?? rosterError ?? accountError
    if (!(error instanceof ApiError) || error.status !== 403) return

    serverAccessError.value =
      error.code === 'password_change_required' ? 'passwordChangeRequired' : 'forbidden'
    clearPrivateData()
    void session.initialize()
  },
)

watch(mutations.error, (error) => {
  if (!mutations.isAdminAccessError(error)) return

  serverAccessError.value =
    error === 'password_change_required' ? 'passwordChangeRequired' : 'forbidden'
  clearPrivateData()
  void session.initialize()
})

function clearPrivateData(): void {
  selectedTeam.value = null
  confirmation.value = null
  memberToRemove.value = null
  rosterSearchInput.value = ''
  accountSearchInput.value = ''
  mutations.clearPrivateState()
  teams.clearPrivateData()
  accountDirectory.clearPrivateData()
}

function retrySession(): void {
  void session.initialize()
}

function selectTeam(team: TeamSummary | null): void {
  if (mutations.isMutating.value) return

  selectedTeam.value = team
  renameDisplayName.value = team?.display_name ?? ''
  rosterSearchInput.value = ''
  accountSearchInput.value = ''
  confirmation.value = null
  memberToRemove.value = null
}

function refetchTeams(): void {
  void teams.teamsQuery.refetch()
}

function refetchRoster(): void {
  void teams.rosterQuery.refetch()
}

function loadMoreTeams(): void {
  void teams.teamsQuery.fetchNextPage()
}

function loadMoreRoster(): void {
  void teams.rosterQuery.fetchNextPage()
}

function loadMoreAccounts(): void {
  void accountDirectory.query.fetchNextPage()
}

async function createTeam(): Promise<void> {
  const result = await mutations.create({
    slug: createSlug.value,
    display_name: createDisplayName.value,
  })
  if (result === null) return

  createSlug.value = ''
  createDisplayName.value = ''
  selectTeam(result)
}

async function renameTeam(): Promise<void> {
  const team = activeTeam.value
  if (team === null) return

  const submittedName = renameDisplayName.value
  const result = await mutations.rename(team.id, { display_name: submittedName })
  if (result !== null) {
    selectedTeam.value = result
    // A saved canonical name is the new baseline; preserve any newer input entered during the request.
    if (renameDisplayName.value === submittedName) renameDisplayName.value = result.display_name
  }
}

function openTeamDeletion(): void {
  if (!mutations.isMutating.value && activeTeam.value !== null) confirmation.value = 'deleteTeam'
}

async function deleteTeam(): Promise<void> {
  const team = activeTeam.value
  if (team === null || confirmation.value !== 'deleteTeam') return

  confirmation.value = null
  const result = await mutations.deleteTeam(team.id)
  if (result !== null) selectTeam(null)
}

function openMemberRemoval(member: TeamMember): void {
  if (mutations.isMutating.value) return

  memberToRemove.value = member
  confirmation.value = 'removeMember'
}

async function removeMember(): Promise<void> {
  const team = activeTeam.value
  const member = memberToRemove.value
  if (team === null || member === null || confirmation.value !== 'removeMember') return

  confirmation.value = null
  const result = await mutations.removeMember(team.id, member.user_id)
  if (result !== null) memberToRemove.value = null
}

async function addMember(account: AdminUser): Promise<void> {
  const team = activeTeam.value
  if (team === null || !account.is_active) return

  await mutations.addMember(team.id, account.id)
}

function closeConfirmation(): void {
  if (!mutations.isMutating.value) {
    confirmation.value = null
    memberToRemove.value = null
  }
}

function errorMessage(error: TeamMutationError | null): string | null {
  switch (error) {
    case 'team_slug_conflict':
      return t('adminTeams.errors.teamSlugConflict')
    case 'team_not_empty':
      return t('adminTeams.errors.teamNotEmpty')
    case 'team_in_use':
      return t('adminTeams.errors.teamInUse')
    case 'inactive_user':
      return t('adminTeams.errors.inactiveUser')
    case 'manager_replacement_required':
      return t('adminTeams.errors.managerReplacementRequired')
    case 'team_membership_conflict':
      return t('adminTeams.errors.teamMembershipConflict')
    case 'resource_not_found':
      return t('adminTeams.errors.resourceNotFound')
    case 'password_change_required':
      return t('adminTeams.errors.passwordChangeRequired')
    case 'forbidden':
      return t('adminTeams.errors.forbidden')
    case 'validation_error':
      return t('adminTeams.errors.validationError')
    case 'authentication_required':
      return t('adminTeams.errors.authenticationRequired')
    case 'network_error':
      return t('adminTeams.errors.networkError')
    case 'unexpected':
      return t('adminTeams.errors.unexpected')
    case null:
      return null
  }
}

function isNoticeFor(operation: TeamMutationOperation): boolean {
  return mutations.errorNotice.value?.operation === operation
}

function successMessage(operation: TeamMutationOperation): string {
  switch (operation) {
    case 'create':
      return t('adminTeams.success.created')
    case 'rename':
      return t('adminTeams.success.renamed')
    case 'delete':
      return t('adminTeams.success.deleted')
    case 'addMember':
      return t('adminTeams.success.memberConfirmed')
    case 'removeMember':
      return t('adminTeams.success.memberRemoved')
  }
}
</script>

<template>
  <main class="admin-teams">
    <p v-if="accessState === 'loading'" role="status">{{ t('adminTeams.loadingAccess') }}</p>

    <div v-else-if="accessState === 'sessionError'" class="admin-teams-error">
      <p role="alert">{{ t('adminTeams.sessionLoadError') }}</p>
      <AppButton type="button" @click="retrySession">{{ t('adminTeams.retry') }}</AppButton>
    </div>

    <div
      v-else-if="accessState === 'forbidden' || serverAccessError === 'forbidden'"
      class="admin-teams-error"
    >
      <h1>{{ t('adminTeams.title') }}</h1>
      <p role="alert">{{ t('adminTeams.forbidden') }}</p>
    </div>

    <div v-else-if="serverAccessError === 'passwordChangeRequired'" class="admin-teams-error">
      <h1>{{ t('adminTeams.title') }}</h1>
      <p role="alert">{{ t('adminTeams.passwordChangeRequired') }}</p>
    </div>

    <template v-else-if="canLoadTeams">
      <header class="admin-teams-heading">
        <div>
          <h1>{{ t('adminTeams.title') }}</h1>
          <p>{{ t('adminTeams.description') }}</p>
        </div>
        <AppButton
          type="button"
          variant="ghost"
          :disabled="teams.teamsQuery.isFetching.value || mutations.isMutating.value"
          @click="refetchTeams"
        >
          {{ t('adminTeams.refetch') }}
        </AppButton>
      </header>

      <p v-if="mutations.successNotice.value" class="admin-teams-success" role="status">
        {{ successMessage(mutations.successNotice.value.operation) }}
      </p>
      <p
        v-if="mutations.refreshFailedNotice.value"
        class="admin-teams-refresh-warning"
        role="alert"
      >
        {{ t('adminTeams.refreshFailed') }}
      </p>

      <section class="admin-teams-create" :aria-labelledby="'admin-team-create-title'">
        <h2 id="admin-team-create-title">{{ t('adminTeams.creation.title') }}</h2>
        <p>{{ t('adminTeams.creation.description') }}</p>
        <form @submit.prevent="createTeam">
          <AppTextField
            id="admin-team-slug"
            v-model="createSlug"
            :label="t('adminTeams.creation.slug')"
            :name="'slug'"
            :autocomplete="'off'"
            :maxlength="100"
            required
          />
          <AppTextField
            id="admin-team-display-name"
            v-model="createDisplayName"
            :label="t('adminTeams.creation.displayName')"
            :name="'display_name'"
            :autocomplete="'off'"
            :maxlength="200"
            required
          />
          <p v-if="isNoticeFor('create') && errorMessage(mutations.error.value)" role="alert">
            {{ errorMessage(mutations.error.value) }}
          </p>
          <AppButton type="submit" :disabled="mutations.isMutating.value">
            {{
              mutations.isMutating.value
                ? t('adminTeams.creating')
                : t('adminTeams.creation.submit')
            }}
          </AppButton>
        </form>
      </section>

      <div class="admin-teams-layout">
        <section class="admin-teams-list" :aria-labelledby="'admin-team-list-title'">
          <div class="admin-teams-section-heading">
            <h2 id="admin-team-list-title">{{ t('adminTeams.list.title') }}</h2>
          </div>
          <AppTextField
            id="admin-team-search"
            v-model="teamSearchInput"
            :label="t('adminTeams.list.search')"
            :name="'query'"
            :autocomplete="'off'"
          />
          <p v-if="teams.teamsQuery.isPending.value" role="status">{{ t('adminTeams.loading') }}</p>
          <div v-else-if="teams.teamsQuery.isError.value && !hasTeams" class="admin-teams-error">
            <p role="alert">{{ t('adminTeams.list.loadError') }}</p>
            <AppButton type="button" @click="refetchTeams">{{ t('adminTeams.retry') }}</AppButton>
          </div>
          <p v-else-if="!hasTeams" class="admin-teams-empty">
            {{ hasTeamSearch ? t('adminTeams.list.searchEmpty') : t('adminTeams.list.empty') }}
          </p>
          <template v-else>
            <ul class="admin-teams-list-items">
              <li v-for="team in teamRows" :key="team.id">
                <button
                  type="button"
                  :class="{ 'admin-teams-list-item--selected': team.id === selectedTeamId }"
                  :aria-pressed="team.id === selectedTeamId"
                  :disabled="mutations.isMutating.value"
                  @click="selectTeam(team)"
                >
                  <span>{{ team.display_name }}</span>
                  <span class="admin-teams-slug">{{ team.slug }}</span>
                </button>
              </li>
            </ul>
            <div v-if="teams.teamsQuery.isFetchNextPageError.value" class="admin-teams-page-error">
              <p role="alert">{{ t('adminTeams.list.paginationError') }}</p>
              <AppButton type="button" variant="ghost" @click="loadMoreTeams">{{
                t('adminTeams.retry')
              }}</AppButton>
            </div>
            <AppButton
              v-else-if="teams.teamsQuery.hasNextPage.value"
              type="button"
              variant="ghost"
              :disabled="teams.teamsQuery.isFetchingNextPage.value || mutations.isMutating.value"
              @click="loadMoreTeams"
            >
              {{
                teams.teamsQuery.isFetchingNextPage.value
                  ? t('adminTeams.loading')
                  : t('adminTeams.loadMore')
              }}
            </AppButton>
          </template>
        </section>

        <section
          v-if="activeTeam"
          class="admin-teams-detail"
          :aria-labelledby="'admin-team-detail-title'"
        >
          <header class="admin-teams-section-heading">
            <div>
              <h2 id="admin-team-detail-title">{{ activeTeam.display_name }}</h2>
              <p class="admin-teams-slug">{{ activeTeam.slug }}</p>
            </div>
          </header>

          <section :aria-labelledby="'admin-team-rename-title'">
            <h3 id="admin-team-rename-title">{{ t('adminTeams.rename.title') }}</h3>
            <form @submit.prevent="renameTeam">
              <AppTextField
                id="admin-team-rename-display-name"
                v-model="renameDisplayName"
                :label="t('adminTeams.rename.displayName')"
                :name="'display_name'"
                :maxlength="200"
                required
              />
              <p class="admin-teams-field-note">{{ t('adminTeams.rename.slugImmutable') }}</p>
              <p v-if="isNoticeFor('rename') && errorMessage(mutations.error.value)" role="alert">
                {{ errorMessage(mutations.error.value) }}
              </p>
              <AppButton type="submit" :disabled="mutations.isMutating.value">{{
                t('adminTeams.rename.submit')
              }}</AppButton>
            </form>
          </section>

          <section :aria-labelledby="'admin-team-roster-title'">
            <div class="admin-teams-section-heading">
              <h3 id="admin-team-roster-title">{{ t('adminTeams.roster.title') }}</h3>
              <AppButton
                type="button"
                variant="ghost"
                :disabled="teams.rosterQuery.isFetching.value || mutations.isMutating.value"
                @click="refetchRoster"
              >
                {{ t('adminTeams.refetch') }}
              </AppButton>
            </div>
            <AppTextField
              id="admin-team-roster-search"
              v-model="rosterSearchInput"
              :label="t('adminTeams.roster.search')"
              :name="'roster_query'"
              :autocomplete="'off'"
            />
            <p v-if="teams.rosterQuery.isPending.value" role="status">
              {{ t('adminTeams.loading') }}
            </p>
            <div
              v-else-if="teams.rosterQuery.isError.value && !hasRosterMembers"
              class="admin-teams-error"
            >
              <p role="alert">{{ t('adminTeams.roster.loadError') }}</p>
              <AppButton type="button" @click="refetchRoster">{{
                t('adminTeams.retry')
              }}</AppButton>
            </div>
            <p v-else-if="!hasRosterMembers" class="admin-teams-empty">
              {{
                hasRosterSearch ? t('adminTeams.roster.searchEmpty') : t('adminTeams.roster.empty')
              }}
            </p>
            <template v-else>
              <ul class="admin-teams-roster-list">
                <li v-for="member in rosterRows" :key="member.user_id">
                  <span>{{ member.display_name }}</span>
                  <AppButton
                    type="button"
                    variant="text"
                    :disabled="mutations.isMutating.value"
                    @click="openMemberRemoval(member)"
                  >
                    {{ t('adminTeams.roster.remove') }}
                  </AppButton>
                </li>
              </ul>
              <div
                v-if="teams.rosterQuery.isFetchNextPageError.value"
                class="admin-teams-page-error"
              >
                <p role="alert">{{ t('adminTeams.roster.paginationError') }}</p>
                <AppButton type="button" variant="ghost" @click="loadMoreRoster">{{
                  t('adminTeams.retry')
                }}</AppButton>
              </div>
              <AppButton
                v-else-if="teams.rosterQuery.hasNextPage.value"
                type="button"
                variant="ghost"
                :disabled="teams.rosterQuery.isFetchingNextPage.value || mutations.isMutating.value"
                @click="loadMoreRoster"
              >
                {{
                  teams.rosterQuery.isFetchingNextPage.value
                    ? t('adminTeams.loading')
                    : t('adminTeams.loadMore')
                }}
              </AppButton>
            </template>
            <p
              v-if="isNoticeFor('removeMember') && errorMessage(mutations.error.value)"
              role="alert"
            >
              {{ errorMessage(mutations.error.value) }}
            </p>
          </section>

          <section :aria-labelledby="'admin-team-add-member-title'">
            <h3 id="admin-team-add-member-title">{{ t('adminTeams.addMember.title') }}</h3>
            <p>{{ t('adminTeams.addMember.description') }}</p>
            <AppTextField
              id="admin-team-account-search"
              v-model="accountSearchInput"
              :label="t('adminTeams.addMember.search')"
              :name="'account_query'"
              :autocomplete="'off'"
            />
            <p v-if="accountDirectory.query.isPending.value" role="status">
              {{ t('adminTeams.loading') }}
            </p>
            <div
              v-else-if="accountDirectory.query.isError.value && !hasAccounts"
              class="admin-teams-error"
            >
              <p role="alert">{{ t('adminTeams.addMember.loadError') }}</p>
              <AppButton type="button" @click="accountDirectory.query.refetch()">{{
                t('adminTeams.retry')
              }}</AppButton>
            </div>
            <p v-else-if="!hasAccounts" class="admin-teams-empty">
              {{
                hasAccountSearch
                  ? t('adminTeams.addMember.searchEmpty')
                  : t('adminTeams.addMember.empty')
              }}
            </p>
            <template v-else>
              <ul class="admin-teams-account-list">
                <li v-for="account in accountRows" :key="account.id">
                  <span>
                    <strong>{{ account.display_name }}</strong>
                    <span class="admin-teams-account-username">{{ account.username }}</span>
                  </span>
                  <span>
                    <span v-if="!account.is_active" class="admin-teams-inactive">
                      {{ t('adminTeams.addMember.inactive') }}
                    </span>
                    <AppButton
                      type="button"
                      variant="text"
                      :disabled="!account.is_active || mutations.isMutating.value"
                      @click="addMember(account)"
                    >
                      {{ t('adminTeams.addMember.add') }}
                    </AppButton>
                  </span>
                </li>
              </ul>
              <div
                v-if="accountDirectory.query.isFetchNextPageError.value"
                class="admin-teams-page-error"
              >
                <p role="alert">{{ t('adminTeams.addMember.paginationError') }}</p>
                <AppButton type="button" variant="ghost" @click="loadMoreAccounts">{{
                  t('adminTeams.retry')
                }}</AppButton>
              </div>
              <AppButton
                v-else-if="accountDirectory.query.hasNextPage.value"
                type="button"
                variant="ghost"
                :disabled="
                  accountDirectory.query.isFetchingNextPage.value || mutations.isMutating.value
                "
                @click="loadMoreAccounts"
              >
                {{
                  accountDirectory.query.isFetchingNextPage.value
                    ? t('adminTeams.loading')
                    : t('adminTeams.loadMore')
                }}
              </AppButton>
            </template>
            <p v-if="isNoticeFor('addMember') && errorMessage(mutations.error.value)" role="alert">
              {{ errorMessage(mutations.error.value) }}
            </p>
          </section>

          <section class="admin-teams-delete" :aria-labelledby="'admin-team-delete-title'">
            <h3 id="admin-team-delete-title">{{ t('adminTeams.deletion.title') }}</h3>
            <p>{{ t('adminTeams.deletion.description') }}</p>
            <p v-if="isNoticeFor('delete') && errorMessage(mutations.error.value)" role="alert">
              {{ errorMessage(mutations.error.value) }}
            </p>
            <AppButton
              type="button"
              variant="text"
              :disabled="mutations.isMutating.value"
              @click="openTeamDeletion"
            >
              {{ t('adminTeams.deletion.open') }}
            </AppButton>
          </section>
        </section>

        <section
          v-else
          class="admin-teams-detail admin-teams-detail--empty"
          :aria-labelledby="'admin-team-select-title'"
        >
          <h2 id="admin-team-select-title">{{ t('adminTeams.selection.title') }}</h2>
          <p>{{ t('adminTeams.selection.description') }}</p>
        </section>
      </div>
    </template>

    <Dialog
      :open="confirmation === 'deleteTeam'"
      class="admin-teams-dialog"
      @close="closeConfirmation"
    >
      <div class="admin-teams-dialog-backdrop" aria-hidden="true" />
      <div class="admin-teams-dialog-position">
        <DialogPanel class="admin-teams-dialog-panel">
          <DialogTitle>{{
            t('adminTeams.deletion.confirm.title', {
              name: activeTeam?.display_name,
              slug: activeTeam?.slug,
            })
          }}</DialogTitle>
          <p>{{ t('adminTeams.deletion.confirm.description') }}</p>
          <p>{{ t('adminTeams.deletion.confirm.emptyRequirement') }}</p>
          <div class="admin-teams-dialog-actions">
            <AppButton
              type="button"
              variant="ghost"
              :disabled="mutations.isMutating.value"
              @click="closeConfirmation"
            >
              {{ t('adminTeams.cancel') }}
            </AppButton>
            <AppButton type="button" :disabled="isDeletingTeam" @click="deleteTeam">
              {{ t('adminTeams.deletion.confirm.submit') }}
            </AppButton>
          </div>
        </DialogPanel>
      </div>
    </Dialog>

    <Dialog
      :open="confirmation === 'removeMember'"
      class="admin-teams-dialog"
      @close="closeConfirmation"
    >
      <div class="admin-teams-dialog-backdrop" aria-hidden="true" />
      <div class="admin-teams-dialog-position">
        <DialogPanel class="admin-teams-dialog-panel">
          <DialogTitle>{{
            t('adminTeams.roster.confirm.title', {
              name: memberToRemove?.display_name,
              team: activeTeam?.display_name,
            })
          }}</DialogTitle>
          <p>{{ t('adminTeams.roster.confirm.description') }}</p>
          <p>{{ t('adminTeams.roster.confirm.managerRequirement') }}</p>
          <p v-if="isNoticeFor('removeMember') && errorMessage(mutations.error.value)" role="alert">
            {{ errorMessage(mutations.error.value) }}
          </p>
          <div class="admin-teams-dialog-actions">
            <AppButton
              type="button"
              variant="ghost"
              :disabled="mutations.isMutating.value"
              @click="closeConfirmation"
            >
              {{ t('adminTeams.cancel') }}
            </AppButton>
            <AppButton type="button" :disabled="mutations.isMutating.value" @click="removeMember">
              {{ t('adminTeams.roster.confirm.submit') }}
            </AppButton>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  </main>
</template>

<style scoped>
.admin-teams {
  padding: var(--space-8) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  max-width: 96rem;
}

.admin-teams-heading,
.admin-teams-section-heading,
.admin-teams-list-item button,
.admin-teams-roster-list li,
.admin-teams-account-list li,
.admin-teams-dialog-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.admin-teams-heading h1,
.admin-teams-section-heading h2,
.admin-teams-create h2,
.admin-teams-detail h3,
.admin-teams-detail--empty h2,
.admin-teams-dialog-panel h2 {
  margin: 0;
}

.admin-teams-heading p,
.admin-teams-create p,
.admin-teams-detail p,
.admin-teams-dialog-panel p {
  color: var(--text-secondary);
}

.admin-teams-create,
.admin-teams-list,
.admin-teams-detail {
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: var(--space-5);
}

.admin-teams-create form,
.admin-teams-detail section,
.admin-teams-list,
.admin-teams-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.admin-teams-layout {
  display: grid;
  grid-template-columns: minmax(17rem, 0.8fr) minmax(0, 1.4fr);
  gap: var(--space-5);
  align-items: start;
}

.admin-teams-list-items,
.admin-teams-roster-list,
.admin-teams-account-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin: 0;
  padding: 0;
  list-style: none;
}

.admin-teams-list-item button {
  width: 100%;
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  text-align: left;
  padding: var(--space-3);
}

.admin-teams-list-item button:hover:not(:disabled),
.admin-teams-list-item--selected {
  border-color: var(--border);
  background: var(--surface-1);
}

.admin-teams-list-item--selected {
  color: var(--accent);
  font-weight: var(--weight-semibold);
}

.admin-teams-slug,
.admin-teams-account-username,
.admin-teams-field-note,
.admin-teams-inactive {
  color: var(--muted);
  font-size: var(--font-size-small);
}

.admin-teams-roster-list li,
.admin-teams-account-list li {
  border-bottom: 1px solid var(--grid);
  padding: var(--space-2) 0;
}

.admin-teams-account-list li > span {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.admin-teams-account-list strong {
  display: block;
}

.admin-teams-empty,
.admin-teams-error,
.admin-teams-page-error,
.admin-teams-success,
.admin-teams-refresh-warning {
  margin: 0;
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--surface-1);
}

.admin-teams-error p,
.admin-teams-page-error p,
.admin-teams-success,
.admin-teams-refresh-warning {
  margin: 0;
}

.admin-teams-error,
.admin-teams-page-error,
.admin-teams-refresh-warning {
  color: var(--critical-text);
}

.admin-teams-success {
  color: var(--good);
}

.admin-teams-delete {
  border-top: 1px solid var(--grid);
  padding-top: var(--space-4);
}

.admin-teams-dialog {
  position: relative;
  z-index: 10;
}

.admin-teams-dialog-backdrop {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--text-primary) 45%, transparent);
}

.admin-teams-dialog-position {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
}

.admin-teams-dialog-panel {
  display: flex;
  width: min(100%, 34rem);
  flex-direction: column;
  gap: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-modal);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
  padding: var(--space-6);
}

.admin-teams-dialog-panel h2 {
  font-size: var(--font-size-title);
}

@media (max-width: 48rem) {
  .admin-teams-heading,
  .admin-teams-section-heading,
  .admin-teams-list-item button,
  .admin-teams-roster-list li,
  .admin-teams-account-list li {
    align-items: flex-start;
    flex-direction: column;
  }

  .admin-teams-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
