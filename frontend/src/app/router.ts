import { createRouter, createWebHistory, type RouteRecordRaw, type RouterHistory } from 'vue-router'

import HomeView from '@/features/home/HomeView.vue'

// History mode: scholarly URLs are shared and cited, so they must be real paths. The frontend image
// falls back to index.html for any path (frontend/nginx/default.conf, decision D13).
//
// The legal notice is public. It has to stay reachable without a session, so when route guards arrive
// with the session handling of milestone M2 it must be exempt from the authentication requirement.
export const routes: readonly RouteRecordRaw[] = [
  { path: '/', name: 'home', component: HomeView },
  {
    path: '/impressum',
    name: 'legalNotice',
    component: () => import('@/features/legal/LegalNoticeView.vue'),
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/features/auth/LoginView.vue'),
  },
  {
    path: '/change-password',
    name: 'changePassword',
    component: () => import('@/features/auth/ChangePasswordView.vue'),
  },
  {
    path: '/projects',
    name: 'projects',
    component: () => import('@/features/projects/ProjectListView.vue'),
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'notFound',
    component: () => import('@/features/errors/NotFoundView.vue'),
  },
]

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  return createRouter({ history, routes: [...routes] })
}
