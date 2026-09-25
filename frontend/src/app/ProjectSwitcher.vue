<script setup lang="ts">
// The topbar's project switcher (docs/23): a menu of the caller's projects, the current one marked,
// and a way to the full list. It shows the first page of `GET /projects` (server order, never
// re-sorted here); a longer list is one link away. The wireframe's completion percentages have no
// backend counterpart and are not shown.
import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/vue'
import { PhCaretDown } from '@phosphor-icons/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import { useProject, useProjectList } from '@/features/projects/useProjects'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const route = useRoute()
const session = useSessionStore()

const signedIn = computed(() => session.canUsePrivateNavigation)
const currentId = computed(() => {
  const raw = route.params.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  return value ? value : ''
})

const list = useProjectList(signedIn)
const current = useProject(
  currentId,
  computed(() => signedIn.value && currentId.value !== ''),
)
const projects = computed(() => list.data.value?.pages.flatMap((page) => page.items) ?? [])
const buttonLabel = computed(() => current.data.value?.display_name ?? t('projectSwitcher.choose'))
</script>

<template>
  <Menu v-if="signedIn" as="div" class="project-switcher">
    <MenuButton class="project-switcher-button" :aria-label="t('projectSwitcher.label')">
      <span class="project-switcher-current">{{ buttonLabel }}</span>
      <PhCaretDown :size="16" aria-hidden="true" />
    </MenuButton>
    <MenuItems class="project-switcher-items">
      <p v-if="list.isError.value" role="alert" class="project-switcher-note">
        {{ t('projectSwitcher.loadError') }}
      </p>
      <p v-else-if="!list.isPending.value && projects.length === 0" class="project-switcher-note">
        {{ t('projectSwitcher.empty') }}
      </p>
      <MenuItem v-for="project in projects" :key="project.id" v-slot="{ active }">
        <RouterLink
          :to="{ name: 'projectOverview', params: { projectId: project.id } }"
          class="project-switcher-item"
          :class="{ 'project-switcher-item--active': active }"
          :aria-current="project.id === currentId ? 'true' : undefined"
        >
          {{ project.display_name }}
        </RouterLink>
      </MenuItem>
      <hr class="project-switcher-separator" />
      <MenuItem v-slot="{ active }">
        <RouterLink
          :to="{ name: 'projects' }"
          class="project-switcher-item"
          :class="{ 'project-switcher-item--active': active }"
        >
          {{ t('projectSwitcher.all') }}
        </RouterLink>
      </MenuItem>
    </MenuItems>
  </Menu>
</template>

<style scoped>
.project-switcher {
  position: relative;
  margin-right: auto;
}

.project-switcher-button {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  max-width: 20rem;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  cursor: pointer;
}

.project-switcher-current {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-switcher-items {
  position: absolute;
  z-index: 10;
  left: 0;
  min-width: 16rem;
  max-height: 24rem;
  overflow-y: auto;
  margin-top: var(--space-1);
  padding: var(--space-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
}

.project-switcher-item {
  display: block;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  color: var(--text-primary);
  text-decoration: none;
}

.project-switcher-item--active {
  background: var(--surface-1);
}

.project-switcher-item[aria-current='true'] {
  color: var(--accent);
  font-weight: var(--weight-semibold);
}

.project-switcher-separator {
  margin: var(--space-1) 0;
  border: none;
  border-top: 1px solid var(--border);
}

.project-switcher-note {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  color: var(--text-secondary);
}
</style>
