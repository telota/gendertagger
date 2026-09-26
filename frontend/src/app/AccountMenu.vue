<script setup lang="ts">
import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/vue'
import { PhCaretDown, PhGearSix, PhSignOut } from '@phosphor-icons/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import AppFeedback from '@/components/base/AppFeedback.vue'
import { useDraftNavigation } from '@/composables/useDraftNavigation'
import { useSessionRecovery } from '@/composables/useSessionRecovery'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const session = useSessionStore()
const drafts = useDraftNavigation()
const recovery = useSessionRecovery()
const confirming = ref(false)
const signingOut = ref(false)
const signOutFailed = ref(false)
// The guest home page already provides the primary sign-in action, and the login page is the form.
const showSignIn = computed(() => route.name !== 'home' && route.name !== 'login')
const showAccountControls = computed(
  () =>
    session.status !== 'ready' ||
    session.isSignedIn ||
    showSignIn.value ||
    signingOut.value ||
    signOutFailed.value,
)
const busy = computed(
  () => confirming.value || signingOut.value || session.isAuthenticating || recovery.isOpen.value,
)
// Recreate Headless UI's menu state when its owner or available actions change. Session recovery
// continues to own its dialog and focus; the header must not leave another open menu underneath it.
const menuKey = computed(
  () => `${session.user?.id ?? ''}:${session.mustChangePassword}:${recovery.isOpen.value}`,
)
watch(
  () => session.user?.id,
  () => {
    signOutFailed.value = false
  },
)

async function signOut(): Promise<void> {
  if (busy.value || !session.isSignedIn) return
  const principalId = session.user?.id
  confirming.value = true
  try {
    if (!(await drafts.confirmLeave()) || principalId !== session.user?.id) return
    signingOut.value = true
    signOutFailed.value = false
    try {
      if (!(await session.logout())) return
    } catch {
      signOutFailed.value = true
      return
    }
    // Only confirmed sign-out abandons drafts. A failed request keeps both account and inputs.
    drafts.discardDrafts()
    await router.push({ name: 'home' })
  } finally {
    confirming.value = false
    signingOut.value = false
  }
}

function retrySession(): void {
  void session.initialize()
}
</script>

<template>
  <div v-if="showAccountControls" class="account-menu app-header-session">
    <template v-if="session.status === 'ready'">
      <Menu
        v-if="session.isSignedIn"
        :key="menuKey"
        v-slot="{ close }"
        as="div"
        class="account-menu-control"
      >
        <MenuButton
          class="account-menu-button"
          :aria-label="t('header.accountMenu', { name: session.user?.display_name })"
          :disabled="busy"
        >
          <span class="account-menu-name">{{ session.user?.display_name }}</span>
          <PhCaretDown :size="16" aria-hidden="true" />
        </MenuButton>
        <MenuItems class="account-menu-items">
          <RouterLink
            v-if="session.canUsePrivateNavigation"
            v-slot="{ href, navigate }"
            :to="{ name: 'userSettings' }"
            custom
          >
            <MenuItem v-slot="{ active }" as="template">
              <a
                :href="href"
                class="account-menu-item"
                :class="{ 'account-menu-item--active': active }"
                @click="
                  (event) => {
                    close()
                    navigate(event)
                  }
                "
              >
                <PhGearSix :size="20" aria-hidden="true" />
                <span>{{ t('header.settings') }}</span>
              </a>
            </MenuItem>
          </RouterLink>
          <MenuItem v-slot="{ active }" :disabled="busy">
            <button
              type="button"
              class="account-menu-item"
              :class="{ 'account-menu-item--active': active }"
              :disabled="busy"
              @click="signOut"
            >
              <PhSignOut :size="20" aria-hidden="true" />
              <span>{{ t('header.signOut') }}</span>
            </button>
          </MenuItem>
        </MenuItems>
      </Menu>
      <RouterLink v-else-if="showSignIn" :to="{ name: 'login' }" class="account-menu-signin">
        {{ t('header.signIn') }}
      </RouterLink>
      <AppFeedback v-if="signingOut" announcement="polite">
        {{ t('header.signingOut') }}
      </AppFeedback>
      <AppFeedback v-else-if="signOutFailed" announcement="assertive" tone="critical">
        {{ t('header.signOutError') }}
        <template #actions>
          <button type="button" class="account-menu-retry" :disabled="busy" @click="signOut">
            {{ t('header.retry') }}
          </button>
        </template>
      </AppFeedback>
    </template>
    <AppFeedback v-else-if="session.status === 'error'" announcement="assertive" tone="critical">
      {{ t('header.serverError') }}
      <template #actions>
        <button type="button" class="account-menu-retry" @click="retrySession">
          {{ t('header.retry') }}
        </button>
      </template>
    </AppFeedback>
    <AppFeedback v-else announcement="polite">{{ t('header.loading') }}</AppFeedback>
  </div>
</template>

<style scoped>
.account-menu {
  display: grid;
  justify-items: end;
  min-width: 0;
  max-width: 100%;
  gap: var(--space-2);
  font-size: var(--font-size-small);
}

.account-menu-control {
  min-width: 0;
  max-width: 100%;
}

.account-menu-button,
.account-menu-signin,
.account-menu-retry {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: var(--control-min-size);
  min-height: var(--control-min-size);
  max-width: 100%;
  padding: var(--space-2) var(--space-3);
  color: var(--accent);
  font: inherit;
  overflow-wrap: anywhere;
}

.account-menu-button {
  gap: var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
  color: var(--text-primary);
  cursor: pointer;
  text-align: start;
}

.account-menu-button svg,
.account-menu-item svg {
  flex-shrink: 0;
}

.account-menu-name {
  min-width: 0;
}

.account-menu-items {
  position: absolute;
  z-index: 10;
  /* The header bounds the popup, including when a long name wraps into another row. */
  top: 100%;
  inset-inline-end: var(--page-gutter);
  width: max-content;
  min-width: min(13rem, calc(100% - 2 * var(--page-gutter)));
  max-width: min(24rem, calc(100% - 2 * var(--page-gutter)));
  margin-top: var(--space-1);
  padding: var(--space-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  background: var(--panel);
}

.account-menu-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  min-height: var(--control-min-size);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: none;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  text-align: start;
  text-decoration: none;
  overflow-wrap: anywhere;
  cursor: pointer;
}

.account-menu-item span {
  min-width: 0;
}

.account-menu-item--active {
  background: var(--surface-1);
}

.account-menu-retry {
  border: none;
  background: none;
  cursor: pointer;
}

.account-menu-button:disabled,
.account-menu-item:disabled,
.account-menu-retry:disabled {
  color: var(--text-secondary);
  cursor: wait;
}
</style>
