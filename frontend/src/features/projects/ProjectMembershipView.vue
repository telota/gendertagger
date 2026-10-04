<script setup lang="ts">
import { PhMinus, PhPlus } from '@phosphor-icons/vue'
import { computed, nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import AppButton from '@/components/base/AppButton.vue'
import AppDialog from '@/components/base/AppDialog.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import AppSelectField from '@/components/base/AppSelectField.vue'
import { useSessionStore } from '@/stores/session'
import { useProjectMembership } from '@/composables/useProjectMembership'
const { t } = useI18n()
const route = useRoute()
const session = useSessionStore()
const projectId = computed(() => String(route.params.projectId))
const principalId = computed(() => session.user?.id ?? null)
const enabled = computed(() => session.status === 'ready' && session.isSignedIn)
const selectedCandidate = ref<string | null>(null)
const selectedRole = ref<'viewer' | 'reviewer' | 'operator'>('viewer')
const addMemberOpen = ref(false)
const transferTarget = ref<string | null>(null)
const memberToRemove = ref<{ user_id: string; display_name: string } | null>(null)
const management = useProjectMembership(projectId, principalId, enabled)
const candidates = computed(
  () => management.candidates.data.value?.pages.flatMap((page) => page.items) ?? [],
)

function toggleAddMember(): void {
  addMemberOpen.value = !addMemberOpen.value
  if (addMemberOpen.value) {
    void nextTick(() => document.getElementById('project-member-candidate')?.focus())
  }
}

async function addMember(): Promise<void> {
  if (selectedCandidate.value === null) return

  const result = await management.setRole(selectedCandidate.value, selectedRole.value)
  if (result === null) return

  selectedCandidate.value = null
  selectedRole.value = 'viewer'
  addMemberOpen.value = false
}

function openMemberRemoval(member: { user_id: string; display_name: string }): void {
  memberToRemove.value = member
}

function closeMemberRemoval(): void {
  if (!management.pending.value) memberToRemove.value = null
}

async function removeMember(): Promise<void> {
  const member = memberToRemove.value
  if (member === null) return

  const result = await management.removeRole(member.user_id)
  if (result !== null) memberToRemove.value = null
}
</script>
<template>
  <main class="project-members app-page-frame">
    <header class="project-members-heading app-page-heading">
      <div class="app-page-heading__copy">
        <h1 class="app-page-heading__title">{{ t('projectMembers.title') }}</h1>
        <p class="app-page-heading__description">{{ t('projectMembers.description') }}</p>
      </div>
      <div class="app-page-heading__actions">
        <AppButton
          type="button"
          :variant="addMemberOpen ? 'ghost' : 'solid'"
          :aria-expanded="addMemberOpen"
          aria-controls="project-member-add-panel"
          @click="toggleAddMember"
        >
          <PhMinus v-if="addMemberOpen" :size="18" aria-hidden="true" />
          <PhPlus v-else :size="18" aria-hidden="true" />
          {{ addMemberOpen ? t('projectMembers.addHide') : t('projectMembers.addOpen') }}
        </AppButton>
      </div>
    </header>

    <AppFeedback v-if="management.state.isPending.value" class="app-card" announcement="polite">
      {{ t('projects.loading') }}
    </AppFeedback>
    <AppFeedback
      v-else-if="management.state.isError.value"
      class="project-members-load-error app-card"
      announcement="assertive"
      tone="critical"
    >
      {{ t('projectMembers.loadError') }}
      <template #actions>
        <AppButton
          type="button"
          variant="ghost"
          :disabled="management.state.isFetching.value"
          @click="management.state.refetch()"
        >
          {{ t('projects.retry') }}
        </AppButton>
      </template>
    </AppFeedback>

    <template v-else-if="management.state.data.value">
      <section
        v-show="addMemberOpen"
        id="project-member-add-panel"
        class="project-members-add app-card"
        aria-labelledby="project-members-add-title"
      >
        <h2 id="project-members-add-title">{{ t('projectMembers.add') }}</h2>
        <div class="project-members-add-fields">
          <AppSelectField
            id="project-member-candidate"
            v-model="selectedCandidate"
            :label="t('projectMembers.person')"
            :disabled="management.pending.value"
          >
            <option :value="null">{{ t('projectMembers.choose') }}</option>
            <option v-for="candidate in candidates" :key="candidate.id" :value="candidate.id">
              {{ candidate.display_name }}
            </option>
          </AppSelectField>
          <AppSelectField
            id="project-member-role"
            v-model="selectedRole"
            :label="t('projectMembers.role')"
            :disabled="management.pending.value"
          >
            <option value="viewer">{{ t('projectMembers.roles.viewer') }}</option>
            <option value="reviewer">{{ t('projectMembers.roles.reviewer') }}</option>
            <option value="operator">{{ t('projectMembers.roles.operator') }}</option>
          </AppSelectField>
        </div>
        <div class="project-members-add-actions app-form-actions">
          <AppButton
            v-if="management.candidates.hasNextPage.value"
            type="button"
            variant="ghost"
            :disabled="management.candidates.isFetchingNextPage.value || management.pending.value"
            @click="management.candidates.fetchNextPage()"
            >{{
              management.candidates.isFetchingNextPage.value
                ? t('projects.loading')
                : t('projects.loadMore')
            }}</AppButton
          >
          <AppButton
            type="button"
            :disabled="selectedCandidate === null || management.pending.value"
            @click="addMember"
            >{{ t('projectMembers.add') }}</AppButton
          >
        </div>
      </section>

      <section
        class="project-members-manager app-card"
        aria-labelledby="project-members-manager-title"
      >
        <div>
          <h2 id="project-members-manager-title">{{ t('projectMembers.manager') }}</h2>
          <dl class="project-members-manager-summary">
            <div>
              <dt>{{ t('projectMembers.person') }}</dt>
              <dd>{{ management.state.data.value.manager.display_name }}</dd>
            </div>
            <div>
              <dt>{{ t('projectMembers.role') }}</dt>
              <dd>
                {{
                  management.state.data.value.manager.project_role === null
                    ? t('projectMembers.noRole')
                    : management.state.data.value.manager.project_role
                }}
              </dd>
            </div>
          </dl>
        </div>
        <div class="project-members-transfer">
          <label for="transfer">{{ t('projectMembers.transfer') }}</label>
          <div class="project-members-transfer-controls">
            <AppSelectField
              id="transfer"
              v-model="transferTarget"
              :label="t('projectMembers.transfer')"
              hide-label
              :disabled="management.pending.value"
            >
              <option :value="null">{{ t('projectMembers.choose') }}</option>
              <option v-for="candidate in candidates" :key="candidate.id" :value="candidate.id">
                {{ candidate.display_name }}
              </option>
            </AppSelectField>
            <AppButton
              type="button"
              variant="ghost"
              :disabled="transferTarget === null || management.pending.value"
              @click="
                transferTarget &&
                management.transfer(transferTarget, management.state.data.value.manager.user_id)
              "
              >{{ t('projectMembers.transfer') }}</AppButton
            >
          </div>
        </div>
      </section>

      <div class="project-members-roster">
        <AppScrollRegion
          class="project-members-table-scroll app-card app-card--sectioned"
          :label="t('layout.tableRegion', { label: t('projectMembers.members') })"
        >
          <table>
            <thead>
              <tr>
                <th scope="col">{{ t('projectMembers.person') }}</th>
                <th scope="col">{{ t('projectMembers.role') }}</th>
                <th scope="col">{{ t('projectMembers.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="member in management.state.data.value.members" :key="member.user_id">
                <th scope="row">{{ member.display_name }}</th>
                <td>
                  <AppSelectField
                    :id="`project-member-role-${member.user_id}`"
                    :label="t('projectMembers.role')"
                    :aria-label="t('projectMembers.role')"
                    hide-label
                    :model-value="member.role"
                    :disabled="management.pending.value"
                    @update:model-value="
                      management.setRole(
                        member.user_id,
                        $event as 'viewer' | 'reviewer' | 'operator',
                      )
                    "
                  >
                    <option value="viewer">{{ t('projectMembers.roles.viewer') }}</option>
                    <option value="reviewer">{{ t('projectMembers.roles.reviewer') }}</option>
                    <option value="operator">{{ t('projectMembers.roles.operator') }}</option>
                  </AppSelectField>
                </td>
                <td class="project-members-actions">
                  <AppButton
                    type="button"
                    variant="ghost"
                    tone="destructive"
                    :disabled="management.pending.value"
                    @click="openMemberRemoval(member)"
                    >{{ t('projectMembers.remove') }}</AppButton
                  >
                </td>
              </tr>
            </tbody>
          </table>
        </AppScrollRegion>
      </div>

      <AppFeedback
        v-if="management.error.value && memberToRemove === null"
        class="project-members-error app-card"
        announcement="assertive"
        tone="critical"
      >
        {{ t('projectMembers.error') }}
      </AppFeedback>
    </template>
  </main>

  <AppDialog
    :open="memberToRemove !== null"
    class="project-members-dialog"
    size="2xl"
    layout="stacked"
    backdrop="ink"
    bordered
    title-size="title"
    title-class="project-members-dialog-title"
    actions-class="project-members-dialog-actions"
    @close="closeMemberRemoval"
  >
    <template #title>
      {{ t('projectMembers.removeConfirm.title', { name: memberToRemove?.display_name }) }}
    </template>
    <p>
      {{ t('projectMembers.removeConfirm.description', { name: memberToRemove?.display_name }) }}
    </p>
    <AppFeedback
      v-if="management.error.value"
      class="project-members-error"
      announcement="assertive"
      tone="critical"
    >
      {{ t('projectMembers.error') }}
    </AppFeedback>
    <template #actions>
      <AppButton
        type="button"
        variant="ghost"
        :disabled="management.pending.value"
        @click="closeMemberRemoval"
      >
        {{ t('projectMembers.removeConfirm.cancel') }}
      </AppButton>
      <AppButton
        type="button"
        tone="destructive"
        :disabled="management.pending.value"
        @click="removeMember"
      >
        {{ t('projectMembers.removeConfirm.submit') }}
      </AppButton>
    </template>
  </AppDialog>
</template>

<style scoped>
.project-members {
  overflow-wrap: anywhere;
}

.project-members h2,
.project-members p {
  margin: 0;
}

.project-members-manager,
.project-members-add {
  display: grid;
  gap: var(--space-5);
}

.project-members-manager {
  margin-top: var(--space-6);
  grid-template-columns: minmax(0, 1fr) minmax(16rem, 0.9fr);
  align-items: end;
}

.project-members-manager-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin: var(--space-4) 0 0;
}

.project-members-manager-summary div {
  display: grid;
  gap: var(--space-1);
}

.project-members-manager-summary dt {
  color: var(--text-secondary);
  font-size: var(--font-size-caption);
  font-weight: var(--weight-semibold);
}

.project-members-manager-summary dd {
  margin: 0;
  font-weight: var(--weight-semibold);
}

.project-members-transfer {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.project-members-transfer-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: var(--space-2);
}

.project-members-transfer-controls .app-select-field {
  flex: 1 1 12rem;
}

.project-members-add-fields {
  --field-gap: var(--space-2);
  --field-label-size: inherit;
  --field-label-color: var(--text-primary);
}

.project-members {
  --field-disabled-opacity: 0.65;
}

.project-members-roster {
  margin-top: var(--space-6);
}

.project-members-table-scroll table {
  width: 100%;
  min-width: 34rem;
  border-collapse: collapse;
  font-size: var(--font-size-body);
}

.project-members-table-scroll th,
.project-members-table-scroll td {
  padding: var(--space-3);
  border-bottom: 1px solid var(--grid);
  text-align: left;
  vertical-align: middle;
}

.project-members-table-scroll thead th {
  color: var(--text-secondary);
  font-size: var(--font-size-caption);
  font-weight: var(--weight-semibold);
  white-space: nowrap;
}

.project-members-table-scroll tbody th {
  font-weight: var(--weight-semibold);
}

.project-members-table-scroll tbody tr:last-child th,
.project-members-table-scroll tbody tr:last-child td {
  border-bottom: 0;
}

.project-members-table-scroll :deep(thead th:last-child),
.project-members-table-scroll :deep(tbody td:last-child) {
  text-align: right;
}

.project-members-actions .app-button {
  white-space: nowrap;
}

.project-members-add-fields {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(10rem, 0.55fr);
  gap: var(--space-4);
}

.project-members-error {
  margin-top: var(--space-4);
}

:global(.app-dialog.project-members-dialog) {
  position: relative;
  z-index: 10;
}

:global(.project-members-dialog .app-dialog-title.project-members-dialog-title) {
  font-weight: bold;
}

:global(.project-members-dialog .app-dialog-actions.project-members-dialog-actions) {
  gap: var(--space-2);
}

@media (max-width: 40rem) {
  .project-members-manager,
  .project-members-add-fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
