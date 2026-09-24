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
    path: '/admin/users',
    name: 'adminUsers',
    component: () => import('@/features/admin/AdminUserDirectoryView.vue'),
  },
  {
    path: '/projects',
    name: 'projects',
    component: () => import('@/features/projects/ProjectListView.vue'),
  },
  {
    path: '/projects/:projectId/overview',
    name: 'projectOverview',
    component: () => import('@/features/projects/ProjectOverviewView.vue'),
  },
  {
    path: '/projects/:projectId/import',
    name: 'projectImport',
    component: () => import('@/features/projects/ImportView.vue'),
  },
  {
    path: '/projects/:projectId/snapshots/:snapshotId/runs',
    name: 'snapshotRuns',
    component: () => import('@/features/runs/RunListView.vue'),
  },
  {
    path: '/projects/:projectId/snapshots/:snapshotId/runs/:runId',
    name: 'runDetail',
    component: () => import('@/features/runs/RunDetailView.vue'),
  },
  {
    path: '/projects/:projectId/runs/:runId/aggregations/:aggregationId',
    name: 'aggregationDetail',
    component: () => import('@/features/runs/AggregationDetailView.vue'),
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
