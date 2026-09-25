<script setup lang="ts">
import { computed, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter, type RouteLocationRaw } from 'vue-router'

import SidebarTooltip from './SidebarTooltip.vue'

const props = withDefaults(
  defineProps<{
    to: RouteLocationRaw | null
    icon: Component
    label: string
    desktopCollapsed?: boolean | undefined
    mobile?: boolean | undefined
    current?: boolean | undefined
    unavailableReason?: string | undefined
  }>(),
  { current: undefined },
)

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const isCurrent = computed(
  () => props.current ?? (props.to !== null && route.name === router.resolve(props.to).name),
)
const explanation = computed(() => props.unavailableReason ?? t('nav.unavailable'))
const tooltipText = computed(() =>
  props.to === null ? `${props.label}: ${explanation.value}` : props.label,
)
const itemClasses = computed(() => ({
  'nav-item--desktop-collapsed': props.desktopCollapsed,
  'nav-item--mobile': props.mobile,
  'nav-item--current': isCurrent.value,
}))
</script>

<template>
  <SidebarTooltip
    v-slot="{ triggerProps }"
    :text="tooltipText"
    :rail-only="to !== null"
    :desktop-collapsed="desktopCollapsed"
    :mobile="mobile"
  >
    <RouterLink v-if="to" v-slot="{ href, navigate }" :to="to" custom>
      <a
        v-bind="triggerProps"
        :href="href"
        class="nav-item"
        :class="itemClasses"
        :aria-current="isCurrent ? 'page' : undefined"
        @click="navigate"
      >
        <component :is="icon" class="nav-item-icon" :size="20" aria-hidden="true" />
        <span class="nav-item-label">{{ label }}</span>
      </a>
    </RouterLink>
    <span
      v-else
      v-bind="triggerProps"
      role="link"
      tabindex="0"
      class="nav-item nav-item-disabled"
      :class="itemClasses"
      aria-disabled="true"
      :aria-current="isCurrent ? 'page' : undefined"
    >
      <component :is="icon" class="nav-item-icon" :size="20" aria-hidden="true" />
      <span class="nav-item-label">{{ label }}</span>
    </span>
  </SidebarTooltip>
</template>

<style scoped>
.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 2.75rem;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-control);
  color: var(--text-secondary);
  font-size: var(--font-size-body-strong);
  text-decoration: none;
}

.nav-item-icon {
  flex-shrink: 0;
}

a.nav-item:hover {
  background: var(--surface-1);
}

.nav-item--current {
  background: var(--surface-1);
  color: var(--accent);
  font-weight: var(--weight-semibold);
}

.nav-item-disabled {
  color: var(--muted);
  cursor: not-allowed;
}

@media (min-width: 1080px) {
  .nav-item--desktop-collapsed:not(.nav-item--mobile) {
    justify-content: center;
    padding: var(--space-2);
  }

  .nav-item--desktop-collapsed:not(.nav-item--mobile) .nav-item-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
}

/* A mobile drawer always presents labels, regardless of the saved desktop choice. */
@media (width < 1080px) {
  .nav-item:not(.nav-item--mobile) {
    justify-content: center;
    padding: var(--space-2);
  }

  .nav-item:not(.nav-item--mobile) .nav-item-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
}
</style>
