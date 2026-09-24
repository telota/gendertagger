<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import AppButton from '@/components/base/AppButton.vue'
import AppTextField from '@/components/base/AppTextField.vue'
import { useSessionStore } from '@/stores/session'
import { useProjectMembership } from './useProjectMembership'
const { t } = useI18n()
const route = useRoute()
const session = useSessionStore()
const projectId = computed(() => String(route.params.projectId))
const principalId = computed(() => session.user?.id ?? null)
const enabled = computed(() => session.status === 'ready' && session.isSignedIn)
const searchInput = ref('')
const selectedCandidate = ref<string | null>(null)
const selectedRole = ref<'viewer' | 'reviewer' | 'operator'>('viewer')
const transferTarget = ref<string | null>(null)
const management = useProjectMembership(projectId, principalId, enabled, searchInput)
const candidates = computed(
  () => management.candidates.data.value?.pages.flatMap((page) => page.items) ?? [],
)
</script>
<template>
  <main class="project-members">
    <h1>{{ t('projectMembers.title') }}</h1>
    <p>{{ t('projectMembers.description') }}</p>
    <p v-if="management.state.isPending.value" role="status">{{ t('projects.loading') }}</p>
    <p v-else-if="management.state.isError.value" role="alert">
      {{ t('projectMembers.loadError') }}
    </p>
    <template v-else-if="management.state.data.value"
      ><section>
        <h2>{{ t('projectMembers.manager') }}</h2>
        <p>{{ management.state.data.value.manager.display_name }}</p>
        <p>
          {{
            management.state.data.value.manager.project_role === null
              ? t('projectMembers.noRole')
              : management.state.data.value.manager.project_role
          }}
        </p>
        <label for="transfer">{{ t('projectMembers.transfer') }}</label
        ><select id="transfer" v-model="transferTarget">
          <option :value="null">{{ t('projectMembers.choose') }}</option>
          <option v-for="candidate in candidates" :key="candidate.id" :value="candidate.id">
            {{ candidate.display_name }}
          </option></select
        ><AppButton
          type="button"
          :disabled="transferTarget === null || management.pending.value"
          @click="
            transferTarget &&
            management.transfer(transferTarget, management.state.data.value.manager.user_id)
          "
          >{{ t('projectMembers.transfer') }}</AppButton
        >
      </section>
      <section>
        <h2>{{ t('projectMembers.members') }}</h2>
        <ul>
          <li v-for="member in management.state.data.value.members" :key="member.user_id">
            <span>{{ member.display_name }}</span>
            <span>{{ t(`projectMembers.roles.${member.role}`) }}</span>
            <select
              :aria-label="t('projectMembers.role')"
              :value="member.role"
              @change="
                management.setRole(
                  member.user_id,
                  ($event.target as HTMLSelectElement).value as 'viewer' | 'reviewer' | 'operator',
                )
              "
            >
              <option value="viewer">{{ t('projectMembers.roles.viewer') }}</option>
              <option value="reviewer">{{ t('projectMembers.roles.reviewer') }}</option>
              <option value="operator">{{ t('projectMembers.roles.operator') }}</option>
            </select>
            <AppButton
              type="button"
              variant="text"
              :disabled="management.pending.value"
              @click="management.removeRole(member.user_id)"
              >{{ t('projectMembers.remove') }}</AppButton
            >
          </li>
        </ul>
      </section>
      <section>
        <h2>{{ t('projectMembers.add') }}</h2>
        <AppTextField
          id="candidate-search"
          v-model="searchInput"
          :label="t('projectMembers.search')"
        />
        <select v-model="selectedCandidate" :aria-label="t('projectMembers.person')">
          <option :value="null">{{ t('projectMembers.choose') }}</option>
          <option v-for="candidate in candidates" :key="candidate.id" :value="candidate.id">
            {{ candidate.display_name }}
          </option>
        </select>
        <select v-model="selectedRole" :aria-label="t('projectMembers.role')">
          <option value="viewer">{{ t('projectMembers.roles.viewer') }}</option>
          <option value="reviewer">{{ t('projectMembers.roles.reviewer') }}</option>
          <option value="operator">{{ t('projectMembers.roles.operator') }}</option>
        </select>
        <AppButton
          type="button"
          :disabled="selectedCandidate === null || management.pending.value"
          @click="selectedCandidate && management.setRole(selectedCandidate, selectedRole)"
          >{{ t('projectMembers.add') }}</AppButton
        >
        <AppButton
          v-if="management.candidates.hasNextPage.value"
          type="button"
          variant="ghost"
          @click="management.candidates.fetchNextPage()"
          >{{ t('projects.loadMore') }}</AppButton
        >
      </section>
      <p v-if="management.error.value" role="alert">{{ t('projectMembers.error') }}</p></template
    >
  </main>
</template>
<style scoped>
.project-members {
  padding: var(--space-8) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  max-width: 64rem;
}
.project-members section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-5);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--panel);
}
.project-members h1,
.project-members h2,
.project-members p {
  margin: 0;
}
.project-members ul {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.project-members li {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  justify-content: space-between;
}
.project-members select {
  border: 1px solid var(--border);
  border-radius: var(--radius-input);
  padding: var(--space-2);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
}
</style>
