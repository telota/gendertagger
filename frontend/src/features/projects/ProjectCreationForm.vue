<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppButton from '@/components/base/AppButton.vue'
import { useDraftRegistration } from '@/composables/useDraftNavigation'
import AppTextField from '@/components/base/AppTextField.vue'

import { useProjectCreation } from './useProjectCreation'

const props = defineProps<{ principalId: string; isAdministrator: boolean }>()
const emit = defineEmits<{ created: [projectId: string] }>()
const { t } = useI18n()
const teamSearchInput = ref('')
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
  teamSearchInput,
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
  teamSearchInput.value = ''
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
    <p>{{ t('projects.creation.description') }}</p>
    <form @submit.prevent="submit">
      <AppTextField
        id="project-create-slug"
        v-model="slug"
        :label="t('projects.creation.slug')"
        :maxlength="100"
        required
      />
      <AppTextField
        id="project-create-name"
        v-model="displayName"
        :label="t('projects.creation.displayName')"
        :maxlength="200"
        required
      />
      <AppTextField
        id="project-create-description"
        v-model="description"
        :label="t('projects.creation.descriptionField')"
        :maxlength="2000"
      />
      <AppTextField
        id="project-create-team-search"
        v-model="teamSearchInput"
        :label="t('projects.creation.teamSearch')"
      />
      <label for="project-create-team">{{ t('projects.creation.team') }}</label>
      <select id="project-create-team" v-model="selectedTeamId" required>
        <option :value="null" disabled>{{ t('projects.creation.chooseTeam') }}</option>
        <option v-for="team in teams" :key="team.id" :value="team.id">
          {{ team.display_name }}
        </option>
      </select>
      <p v-if="creation.teamsQuery.isPending.value" role="status">{{ t('projects.loading') }}</p>
      <p v-else-if="teams.length === 0">{{ t('projects.creation.noTeams') }}</p>
      <label v-if="isAdministrator" for="project-create-manager">{{
        t('projects.creation.initialManager')
      }}</label>
      <select
        v-if="isAdministrator"
        id="project-create-manager"
        v-model="selectedManagerId"
        :disabled="selectedTeamId === null"
      >
        <option :value="null">{{ t('projects.creation.defaultManager') }}</option>
        <option v-for="member in activeManagers" :key="member.user_id" :value="member.user_id">
          {{ member.display_name }}
        </option>
      </select>
      <AppButton
        v-if="isAdministrator && creation.managerQuery.hasNextPage.value"
        type="button"
        variant="ghost"
        :disabled="creation.managerQuery.isFetchingNextPage.value"
        @click="() => creation.managerQuery.fetchNextPage()"
        >{{ t('projects.loadMore') }}</AppButton
      >
      <p
        v-if="
          isAdministrator &&
          selectedTeamId !== null &&
          !creation.managerQuery.isPending.value &&
          activeManagers.length === 0
        "
      >
        {{ t('projects.creation.noManagers') }}
      </p>
      <p v-if="creation.error.value" role="alert">{{ t('projects.creation.error') }}</p>
      <p v-if="creation.refreshFailed.value" role="alert">
        {{ t('projects.creation.refreshFailed') }}
      </p>
      <AppButton type="submit" :disabled="selectedTeamId === null || creation.isSubmitting.value">{{
        t('projects.creation.submit')
      }}</AppButton>
    </form>
  </section>
</template>

<style scoped>
.project-creation,
.project-creation form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.project-creation {
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
  padding: var(--space-5);
}
.project-creation h2,
.project-creation p {
  margin: 0;
}
.project-creation p {
  color: var(--text-secondary);
}
.project-creation select {
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  padding: var(--space-2) var(--space-3);
}
</style>
