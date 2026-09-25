import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { h, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import DraftLeaveDialog from '@/app/DraftLeaveDialog.vue'
import { createAppI18n } from '@/app/i18n'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { provideDraftNavigation, useDraftRegistration } from '@/composables/useDraftNavigation'
import { useSessionStore } from '@/stores/session'

import { waitFor } from '../helpers/wait'

const wrappers: VueWrapper[] = []
const USER_A = { id: 'user-a', display_name: 'User A', roles: [] }
const USER_B = { id: 'user-b', display_name: 'User B', roles: [] }

afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.replaceChildren()
})

async function fixture() {
  const pinia = createPinia()
  const empty = { render: () => h('div') }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/projects/:id', component: empty },
      { path: '/settings', component: empty },
      { path: '/login', name: 'login', component: empty },
      { path: '/password', name: 'changePassword', component: empty },
    ],
  })
  await router.push('/projects/a')
  await router.isReady()
  const text = ref('')
  const show = ref(true)
  let navigation!: ReturnType<typeof provideDraftNavigation>
  const editor = {
    setup() {
      useDraftRegistration(
        () => text.value !== '',
        () => {
          text.value = ''
        },
      )
      return () => h('input', { value: text.value })
    },
  }
  const application = {
    setup() {
      const session = useSessionStore()
      session.user = USER_A
      session.status = 'ready'
      navigation = provideDraftNavigation()
      return () => h('div', [show.value ? h(editor) : null, h(DraftLeaveDialog)])
    },
  }
  const wrapper = mount(application, {
    attachTo: document.body,
    global: {
      plugins: [pinia, router, createAppI18n('en')],
      provide: { [API_CLIENT_KEY as symbol]: createApiClient() },
    },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router, text, show, navigation, session: useSessionStore(pinia) }
}

describe('view-owned draft navigation', () => {
  it('keeps the route and draft when Stay cancels a path change', async () => {
    const { router, text, navigation } = await fixture()
    text.value = 'Unsubmitted evidence'
    const attempt = router.push('/settings')
    await waitFor(() => expect(navigation.isOpen.value).toBe(true))
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
    const stay = document.querySelector<HTMLButtonElement>('.draft-leave-actions button')
    expect(stay).not.toBeNull()
    stay?.click()
    await attempt
    expect(router.currentRoute.value.path).toBe('/projects/a')
    expect(text.value).toBe('Unsubmitted evidence')
    expect(navigation.isOpen.value).toBe(false)
  })

  it('discards on a successful route-parameter change and starts the reused view clean', async () => {
    const { router, text, navigation } = await fixture()
    text.value = 'Draft for project a'
    const attempt = router.push('/projects/b')
    await waitFor(() => expect(navigation.isOpen.value).toBe(true))
    navigation.resolveLeave(true)
    await attempt
    expect(router.currentRoute.value.path).toBe('/projects/b')
    expect(text.value).toBe('')
    await router.push('/settings')
    expect(navigation.isOpen.value).toBe(false)
  })

  it('preserves drafts and normal navigation for query-only filters', async () => {
    const { router, text, navigation } = await fixture()
    text.value = 'Draft'
    await router.push('/projects/a?query=alice')
    expect(router.currentRoute.value.query.query).toBe('alice')
    expect(navigation.isOpen.value).toBe(false)
    expect(text.value).toBe('Draft')
  })

  it('keeps accepted drafts if another navigation guard rejects the destination', async () => {
    const { router, text, navigation } = await fixture()
    router.beforeEach(() => false)
    text.value = 'Do not lose this'
    const attempt = router.push('/settings')
    await waitFor(() => expect(navigation.isOpen.value).toBe(true))
    navigation.resolveLeave(true)
    await attempt
    expect(router.currentRoute.value.path).toBe('/projects/a')
    expect(text.value).toBe('Do not lose this')
  })

  it('does not discard after confirmation alone, allowing failed sign-out to retain input', async () => {
    const { text, navigation } = await fixture()
    text.value = 'Draft'
    const attempt = navigation.confirmLeave()
    navigation.resolveLeave(true)
    await expect(attempt).resolves.toBe(true)
    expect(text.value).toBe('Draft')
    navigation.discardDrafts()
    expect(text.value).toBe('')
  })

  it('unregisters an unmounted editor and releases a pending prompt on app teardown', async () => {
    const { wrapper, show, text, navigation } = await fixture()
    text.value = 'Draft'
    show.value = false
    await flushPromises()
    await expect(navigation.confirmLeave()).resolves.toBe(true)
    show.value = true
    await flushPromises()
    const pending = navigation.confirmLeave()
    wrapper.unmount()
    wrappers.splice(wrappers.indexOf(wrapper), 1)
    await expect(pending).resolves.toBe(false)
  })

  it('preserves same-principal recovery and clears input and pending prompts on identity change', async () => {
    const { text, navigation, session } = await fixture()
    text.value = 'User A private draft'
    session.user = { ...USER_A }
    expect(text.value).toBe('User A private draft')
    const pending = navigation.confirmLeave()
    session.user = USER_B
    await expect(pending).resolves.toBe(false)
    expect(text.value).toBe('')
    expect(navigation.isOpen.value).toBe(false)
  })

  it('keeps separately mounted applications isolated', async () => {
    const first = await fixture()
    const second = await fixture()
    first.text.value = 'First app draft'
    await expect(second.navigation.confirmLeave()).resolves.toBe(true)
    expect(first.text.value).toBe('First app draft')
    second.session.user = USER_B
    expect(first.text.value).toBe('First app draft')
  })

  it('allows a required password-change redirect without trapping the account', async () => {
    const { router, text, navigation, session } = await fixture()
    text.value = 'Draft'
    session.mustChangePassword = true
    await router.push({ name: 'changePassword' })
    expect(router.currentRoute.value.name).toBe('changePassword')
    expect(navigation.isOpen.value).toBe(false)
    expect(text.value).toBe('')
  })
})
