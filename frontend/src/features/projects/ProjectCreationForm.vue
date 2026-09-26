<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import AppFieldHelp from '@/components/base/AppFieldHelp.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useDraftRegistration } from '@/composables/useDraftNavigation'

import { useProjectCreation } from './useProjectCreation'

const props = defineProps<{ principalId: string; isAdministrator: boolean }>()
const emit = defineEmits<{ created: [projectId: string] }>()
const { t } = useI18n()
const unfilteredTeams = ref('')
const selectedTeamId = ref<string | null>(null)
const slug = ref('')
const displayName = ref('')
const description = ref('')
const selectedManagerId = ref<string | null>(null)
const principal = computed(() => props.principalId)
const canCreate = computed(() => true)
const administrator = computed(() => props.isAdministrator)
const creation = useProjectCreation(
  principal,
  canCreate,
  administrator,
  unfilteredTeams,
  selectedTeamId,
)
const teams = computed(
  () => creation.teamsQuery.data.value?.pages.flatMap((page) => page.items) ?? [],
)
const activeManagers = computed(
  () =>
    creation.managerQuery.data.value?.pages
      .flatMap((page) => page.items)
      .filter((member) => member.is_active) ?? [],
)

watch(selectedTeamId, () => {
  selectedManagerId.value = null
})

const draftFingerprint = computed(() =>
  JSON.stringify([
    slug.value,
    displayName.value,
    description.value,
    selectedTeamId.value,
    selectedManagerId.value,
  ]),
)
const acceptedDraft = ref<string | null>(null)

function resetDraft(): void {
  creation.clear()
  acceptedDraft.value = null
  slug.value = ''
  displayName.value = ''
  description.value = ''
  selectedTeamId.value = null
  selectedManagerId.value = null
}

useDraftRegistration(
  () =>
    creation.isSubmitting.value ||
    (draftFingerprint.value !== acceptedDraft.value &&
      (slug.value !== '' ||
        displayName.value !== '' ||
        description.value !== '' ||
        selectedTeamId.value !== null)),
  resetDraft,
)

async function submit(): Promise<void> {
  const teamId = selectedTeamId.value
  if (teamId === null) return
  const submittedDraft = draftFingerprint.value
  const project = await creation.create({
    slug: slug.value,
    display_name: displayName.value,
    ...(description.value === '' ? {} : { description: description.value }),
    team_id: teamId,
    ...(selectedManagerId.value === null
      ? {}
      : { initial_manager_user_id: selectedManagerId.value }),
  })
  if (project !== null) {
    if (draftFingerprint.value === submittedDraft) resetDraft()
    else acceptedDraft.value = submittedDraft
    emit('created', project.id)
  }
}
</script>

<template>
  <section class="project-creation" aria-labelledby="project-creation-title">
    <h2 id="project-creation-title">{{ t('projects.creation.title') }}</h2>
    <form @submit.prevent="submit">
      <fieldset class="project-creation-group">
        <legend>{{ t('projects.creation.detailsTitle') }}</legend>
        <div class="project-creation-details">
          <AppTextField
            id="project-create-name"
            v-model="displayName"
            name="display_name"
            :label="t('projects.creation.displayName')"
            :maxlength="200"
            required
          />
          <div class="project-creation-field">
            <label for="project-create-slug">{{ t('projects.creation.slug') }}</label>
            <div class="project-creation-slug-control">
              <input
                id="project-create-slug"
                v-model="slug"
                name="slug"
                maxlength="100"
                autocomplete="off"
                :spellcheck="false"
                :placeholder="t('projects.creation.slugExample')"
                pattern="[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
                aria-describedby="project-create-slug-help"
                required
              />
              <AppFieldHelp
                description-id="project-create-slug-help"
                :label="t('projects.creation.slugHelpLabel')"
                :text="t('projects.creation.slugConstraints')"
              />
            </div>
          </div>
          <div class="project-creation-field project-creation-description">
            <label for="project-create-description">{{
              t('projects.creation.descriptionField')
            }}</label>
            <textarea
              id="project-create-description"
              v-model="description"
              name="description"
              maxlength="2000"
              rows="2"
            ></textarea>
          </div>
        </div>
      </fieldset>

      <fieldset class="project-creation-group">
        <legend>{{ t('projects.creation.teamTitle') }}</legend>
        <div class="project-creation-field">
          <label for="project-create-team">{{ t('projects.creation.team') }}</label>
          <select id="project-create-team" v-model="selectedTeamId" required>
            <option :value="null" disabled>{{ t('projects.creation.chooseTeam') }}</option>
            <option v-for="team in teams" :key="team.id" :value="team.id">
              {{ team.display_name }}
            </option>
          </select>
        </div>
        <AppFeedback v-if="creation.teamsQuery.isPending.value" announcement="polite">
          {{ t('projects.creation.teamsLoading') }}
        </AppFeedback>
        <AppFeedback
          v-else-if="
            creation.teamsQuery.isError.value && !creation.teamsQuery.isFetchNextPageError.value
          "
          class="project-creation-teams-error"
          announcement="assertive"
          tone="critical"
        >
          {{ t('projects.creation.teamsLoadError') }}
          <template #actions>
            <AppButton
              type="button"
              variant="ghost"
              :disabled="creation.teamsQuery.isFetching.value"
              @click="creation.teamsQuery.refetch()"
              >{{
                creation.teamsQuery.isFetching.value
                  ? t('projects.creation.teamsLoading')
                  : t('projects.retry')
              }}</AppButton
            >
          </template>
        </AppFeedback>
        <AppFeedback v-else-if="teams.length === 0 && !creation.teamsQuery.isError.value">
          {{ t('projects.creation.noTeams') }}
        </AppFeedback>
        <AppFeedback
          v-if="creation.teamsQuery.isFetchNextPageError.value"
          class="project-creation-teams-page-error"
          announcement="assertive"
          tone="critical"
        >
          {{ t('projects.creation.teamsPageError') }}
          <template #actions>
            <AppButton
              type="button"
              variant="ghost"
              :disabled="creation.teamsQuery.isFetching.value"
              @click="creation.teamsQuery.fetchNextPage()"
              >{{
                creation.teamsQuery.isFetchingNextPage.value
                  ? t('projects.creation.teamsLoading')
                  : t('projects.retry')
              }}</AppButton
            >
          </template>
        </AppFeedback>
        <AppButton
          v-else-if="creation.teamsQuery.hasNextPage.value"
          class="project-creation-teams-more"
          type="button"
          variant="ghost"
          :disabled="creation.teamsQuery.isFetching.value"
          @click="creation.teamsQuery.fetchNextPage()"
          >{{
            creation.teamsQuery.isFetchingNextPage.value
              ? t('projects.creation.teamsLoading')
              : t('projects.creation.teamsLoadMore')
          }}</AppButton
        >

        <div v-if="isAdministrator" class="project-creation-manager">
          <div class="project-creation-field">
            <label for="project-create-manager">{{ t('projects.creation.initialManager') }}</label>
            <select
              id="project-create-manager"
              v-model="selectedManagerId"
              :disabled="selectedTeamId === null"
              aria-describedby="project-create-manager-help"
            >
              <option :value="null">{{ t('projects.creation.defaultManager') }}</option>
              <option
                v-for="member in activeManagers"
                :key="member.user_id"
                :value="member.user_id"
              >
                {{ member.display_name }}
              </option>
            </select>
            <p id="project-create-manager-help" class="project-creation-help">
              {{ t('projects.creation.managerHelp') }}
            </p>
          </div>
          <template v-if="selectedTeamId !== null">
            <AppFeedback v-if="creation.managerQuery.isPending.value" announcement="polite">
              {{ t('projects.creation.managersLoading') }}
            </AppFeedback>
            <AppFeedback
              v-else-if="
                creation.managerQuery.isError.value &&
                !creation.managerQuery.isFetchNextPageError.value
              "
              class="project-creation-managers-error"
              announcement="assertive"
              tone="critical"
            >
              {{ t('projects.creation.managersLoadError') }}
              <template #actions>
                <AppButton
                  type="button"
                  variant="ghost"
                  :disabled="creation.managerQuery.isFetching.value"
                  @click="creation.managerQuery.refetch()"
                  >{{
                    creation.managerQuery.isFetching.value
                      ? t('projects.creation.managersLoading')
                      : t('projects.retry')
                  }}</AppButton
                >
              </template>
            </AppFeedback>
            <AppFeedback
              v-else-if="activeManagers.length === 0 && !creation.managerQuery.isError.value"
            >
              {{
                creation.managerQuery.hasNextPage.value
                  ? t('projects.creation.noLoadedManagers')
                  : t('projects.creation.noManagers')
              }}
            </AppFeedback>
            <AppFeedback
              v-if="creation.managerQuery.isFetchNextPageError.value"
              class="project-creation-managers-page-error"
              announcement="assertive"
              tone="critical"
            >
              {{ t('projects.creation.managersPageError') }}
              <template #actions>
                <AppButton
                  type="button"
                  variant="ghost"
                  :disabled="creation.managerQuery.isFetching.value"
                  @click="creation.managerQuery.fetchNextPage()"
                  >{{
                    creation.managerQuery.isFetchingNextPage.value
                      ? t('projects.creation.managersLoading')
                      : t('projects.retry')
                  }}</AppButton
                >
              </template>
            </AppFeedback>
            <AppButton
              v-else-if="creation.managerQuery.hasNextPage.value"
              class="project-creation-managers-more"
              type="button"
              variant="ghost"
              :disabled="creation.managerQuery.isFetching.value"
              @click="creation.managerQuery.fetchNextPage()"
              >{{
                creation.managerQuery.isFetchingNextPage.value
                  ? t('projects.creation.managersLoading')
                  : t('projects.creation.managersLoadMore')
              }}</AppButton
            >
          </template>
        </div>
      </fieldset>

      <AppFeedback
        v-if="creation.error.value"
        class="project-creation-feedback"
        announcement="assertive"
        tone="critical"
      >
        {{ t('projects.creation.error') }}
      </AppFeedback>
      <AppFeedback
        v-if="creation.refreshFailed.value"
        class="project-creation-feedback"
        announcement="assertive"
        tone="critical"
      >
        {{ t('projects.creation.refreshFailed') }}
      </AppFeedback>
      <AppButton
        class="project-creation-submit"
        type="submit"
        :disabled="selectedTeamId === null || creation.isSubmitting.value"
        >{{
          creation.isSubmitting.value
            ? t('projects.creation.submitting')
            : t('projects.creation.submit')
        }}</AppButton
      >
    </form>
  </section>
</template>

<style scoped>
.project-creation,
.project-creation-group,
.project-creation-manager {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.project-creation {
  container: project-creation / inline-size;
  gap: var(--space-4);
  padding: var(--space-5) var(--page-gutter);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
  overflow-wrap: anywhere;
}

.project-creation h2,
.project-creation p {
  margin: 0;
}

.project-creation h2 {
  font-size: var(--font-size-title);
  font-weight: var(--weight-semibold);
}

.project-creation-help {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  max-width: 65ch;
}

.project-creation form {
  display: grid;
  min-width: 0;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-5);
  align-items: start;
}

.project-creation-group {
  gap: var(--space-3);
  margin: 0;
  padding: 0;
  border: 0;
}

.project-creation-group legend {
  margin-bottom: var(--space-2);
  padding: 0;
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
}

.project-creation-details {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-3);
}

.project-creation-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: var(--space-1);
}

.project-creation-slug-control {
  display: flex;
  min-inline-size: 0;
  align-items: center;
  gap: var(--space-1);
}

.project-creation-slug-control input {
  flex: 1;
  inline-size: 100%;
}

.project-creation-field > label {
  color: var(--text-secondary);
  font-size: var(--font-size-small);
}

.project-creation input,
.project-creation select,
.project-creation textarea {
  min-width: 0;
  min-height: var(--control-min-size);
  max-width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  padding: var(--space-2) var(--space-3);
}

.project-creation textarea {
  resize: vertical;
}

.project-creation-manager {
  gap: var(--space-3);
}

.project-creation-submit,
.project-creation-teams-more,
.project-creation-managers-more {
  align-self: flex-start;
}

.project-creation-feedback,
.project-creation-submit {
  grid-column: 1 / -1;
}

.project-creation-submit {
  justify-self: start;
}

@container project-creation (min-width: 32rem) {
  .project-creation-details {
    grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  }

  .project-creation-description {
    grid-column: 1 / -1;
  }
}

@container project-creation (min-width: 44rem) {
  .project-creation form {
    grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
    column-gap: var(--space-6);
  }
}
</style>
