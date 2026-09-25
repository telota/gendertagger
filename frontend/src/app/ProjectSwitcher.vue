<script setup lang="ts">
// Project identity and switching belong together above the project's sidebar destinations.
// The menu shows the first server-ordered page; the sidebar Projects entry opens the full list.
import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/vue'
import { PhCaretDown, PhFolderSimple } from '@phosphor-icons/vue'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import { useSessionRecovery } from '@/composables/useSessionRecovery'
import { useProjectList, type AccessibleProject } from '@/features/projects/useProjects'

import SidebarTooltip from './SidebarTooltip.vue'

const props = defineProps<{
  project: AccessibleProject
  desktopCollapsed?: boolean
  mobile?: boolean
}>()

const { t } = useI18n()
const recovery = useSessionRecovery()
const root = ref<HTMLElement | null>(null)
const menu = ref<{ $el: HTMLElement | null } | null>(null)
const isNarrow = ref(false)
const position = ref({ left: '0px', top: '0px', maxHeight: 'calc(100dvh - 1rem)' })
const list = useProjectList(computed(() => true))
const projects = computed(() => list.data.value?.pages.flatMap((page) => page.items) ?? [])
const label = computed(() =>
  t('projectSwitcher.currentLabel', { project: props.project.display_name }),
)
let observer: ResizeObserver | undefined
let mobileQuery: MediaQueryList | undefined

function menuElement(): HTMLElement | null {
  const element = menu.value?.$el
  return element instanceof HTMLElement ? element : null
}

function updateViewport(event: MediaQueryListEvent): void {
  const ownedFocus =
    !props.mobile &&
    (root.value?.contains(document.activeElement) ||
      menuElement()?.contains(document.activeElement))
  isNarrow.value = event.matches
  if (event.matches && ownedFocus) {
    void nextTick(() => document.querySelector<HTMLElement>('.app-header-navigation')?.focus())
  }
}

function reposition(): void {
  const button = root.value?.querySelector('button')
  const popup = menuElement()
  if (!button || !popup) return
  const anchor = button.getBoundingClientRect()
  const gap = 8
  const width = popup.getBoundingClientRect().width
  const viewportHeight = window.innerHeight
  const anchorTop = Math.min(viewportHeight - gap, Math.max(gap, anchor.top))
  const anchorBottom = Math.min(viewportHeight - gap, Math.max(gap, anchor.bottom))
  const below = Math.max(0, viewportHeight - anchorBottom - 2 * gap)
  const above = Math.max(0, anchorTop - 2 * gap)
  // Desktop portals escape the sticky sidebar's stacking context. Mobile stays inside its
  // Dialog focus boundary. Prefer below, using above when it fits better.
  const placeAbove = below < Math.min(popup.scrollHeight, 240) && above > below
  const maxHeight = Math.max(0, placeAbove ? above : below)
  const top = placeAbove
    ? Math.max(gap, anchorTop - Math.min(popup.scrollHeight, maxHeight) - gap)
    : Math.max(gap, anchorBottom + gap)
  const left = Math.max(gap, Math.min(anchor.left, window.innerWidth - width - gap))
  const next = { left: `${left}px`, top: `${top}px`, maxHeight: `${maxHeight}px` }
  if (
    Object.keys(next).some(
      (key) => next[key as keyof typeof next] !== position.value[key as keyof typeof next],
    )
  ) {
    position.value = next
  }
}

// Headless UI keeps its component mounted while replacing the actual menu DOM on open/close.
// Observe its exposed element after rendering, including when it is portaled outside this root.
watch(
  () => menu.value?.$el,
  (element, previous) => {
    if (previous instanceof HTMLElement) observer?.unobserve(previous)
    if (element instanceof HTMLElement) observer?.observe(element)
    reposition()
  },
  { flush: 'post' },
)
watch([projects, list.isPending, list.isError], reposition, { flush: 'post' })

onMounted(() => {
  mobileQuery = window.matchMedia('(width < 720px)')
  isNarrow.value = mobileQuery.matches
  mobileQuery.addEventListener('change', updateViewport)
  observer = new ResizeObserver(reposition)
  if (root.value) observer.observe(root.value)
  window.addEventListener('resize', reposition)
  window.addEventListener('scroll', reposition, true)
})
onUnmounted(() => {
  observer?.disconnect()
  mobileQuery?.removeEventListener('change', updateViewport)
  window.removeEventListener('resize', reposition)
  window.removeEventListener('scroll', reposition, true)
})
</script>

<template>
  <div
    ref="root"
    class="project-switcher"
    :class="{
      'project-switcher--collapsed': desktopCollapsed && !mobile,
      'project-switcher--mobile': mobile,
    }"
  >
    <p class="project-switcher-current">{{ project.display_name }}</p>
    <Menu v-if="(mobile || !isNarrow) && !recovery.isOpen.value" v-slot="{ open, close }" as="div">
      <SidebarTooltip
        v-slot="{ triggerProps }"
        :text="label"
        rail-only
        :desktop-collapsed="desktopCollapsed"
        :mobile="mobile"
        :disabled="open"
      >
        <MenuButton v-bind="triggerProps" class="project-switcher-button" :aria-label="label">
          <PhFolderSimple :size="20" aria-hidden="true" />
          <span class="project-switcher-action">{{ t('projectSwitcher.action') }}</span>
          <PhCaretDown class="project-switcher-caret" :size="14" aria-hidden="true" />
        </MenuButton>
      </SidebarTooltip>
      <Teleport to="body" :disabled="mobile">
        <MenuItems ref="menu" class="project-switcher-items" :style="position">
          <p v-if="list.isPending.value" role="status" class="project-switcher-note">
            {{ t('projectSwitcher.loading') }}
          </p>
          <template v-else-if="list.isError.value">
            <p role="alert" class="project-switcher-note">{{ t('projectSwitcher.loadError') }}</p>
            <MenuItem v-slot="{ active }">
              <button
                type="button"
                class="project-switcher-item"
                :class="{ 'project-switcher-item--active': active }"
                @click="list.refetch()"
              >
                {{ t('header.retry') }}
              </button>
            </MenuItem>
          </template>
          <p v-else-if="projects.length === 0" class="project-switcher-note">
            {{ t('projectSwitcher.empty') }}
          </p>
          <template v-else>
            <RouterLink
              v-for="item in projects"
              :key="item.id"
              v-slot="{ href, navigate }"
              :to="{ name: 'projectOverview', params: { projectId: item.id } }"
              custom
            >
              <MenuItem v-slot="{ active }" as="template">
                <a
                  :href="href"
                  class="project-switcher-item"
                  :class="{ 'project-switcher-item--active': active }"
                  :aria-current="item.id === project.id ? 'true' : undefined"
                  @click="
                    (event) => {
                      close()
                      navigate(event)
                    }
                  "
                >
                  {{ item.display_name }}
                </a>
              </MenuItem>
            </RouterLink>
          </template>
        </MenuItems>
      </Teleport>
    </Menu>
  </div>
</template>

<style scoped>
.project-switcher {
  min-width: 0;
  max-width: 100%;
  margin-bottom: var(--space-3);
}

.project-switcher-current {
  margin: 0 0 var(--space-2);
  padding-inline: var(--space-3);
  color: var(--text-primary);
  font-size: var(--font-size-body-strong);
  font-weight: var(--weight-semibold);
  overflow-wrap: anywhere;
}

.project-switcher-button {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  min-width: var(--control-min-size);
  min-height: var(--control-touch-size);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--text-primary);
  font: inherit;
  text-align: start;
  cursor: pointer;
}

.project-switcher-button:hover {
  background: var(--surface-1);
}

.project-switcher-button > svg {
  flex-shrink: 0;
}

.project-switcher-action {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.project-switcher-items {
  position: fixed;
  z-index: 40;
  width: max-content;
  min-width: min(16rem, calc(100vw - var(--space-4)));
  max-width: min(24rem, calc(100vw - var(--space-4)));
  overflow-y: auto;
  padding: var(--space-1);
  border-radius: var(--radius-control);
  background: var(--panel);
  box-shadow: var(--shadow-menu);
}

.project-switcher-item {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: var(--control-min-size);
  padding: var(--space-2) var(--space-3);
  border: 0;
  border-radius: var(--radius-control);
  background: none;
  color: var(--text-primary);
  font: inherit;
  text-align: start;
  text-decoration: none;
  overflow-wrap: anywhere;
  cursor: pointer;
}

.project-switcher-item--active {
  background: var(--surface-1);
}

.project-switcher-item[aria-current='true'] {
  color: var(--accent);
  font-weight: var(--weight-semibold);
}

.project-switcher-note {
  overflow-wrap: anywhere;
  margin: 0;
  padding: var(--space-2) var(--space-3);
  color: var(--text-secondary);
}

@media (min-width: 1080px) {
  .project-switcher--collapsed .project-switcher-current,
  .project-switcher--collapsed .project-switcher-action,
  .project-switcher--collapsed .project-switcher-caret {
    display: none;
  }

  .project-switcher--collapsed .project-switcher-button {
    justify-content: center;
    padding: var(--space-2);
  }
}

@media (720px <= width < 1080px) {
  .project-switcher:not(.project-switcher--mobile) .project-switcher-current,
  .project-switcher:not(.project-switcher--mobile) .project-switcher-action,
  .project-switcher:not(.project-switcher--mobile) .project-switcher-caret {
    display: none;
  }

  .project-switcher:not(.project-switcher--mobile) .project-switcher-button {
    justify-content: center;
    padding: var(--space-2);
  }
}
</style>
