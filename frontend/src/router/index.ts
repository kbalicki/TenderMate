import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/pages/TenderListPage.vue'),
    },
    {
      path: '/tenders',
      redirect: '/',
    },
    {
      path: '/tenders/new',
      name: 'new-tender',
      component: () => import('@/pages/NewTenderPage.vue'),
    },
    {
      path: '/tenders/:id',
      name: 'tender-detail',
      component: () => import('@/pages/TenderDetailPage.vue'),
      props: true,
    },
    {
      path: '/tenders/:id/analysis',
      name: 'analysis',
      component: () => import('@/pages/AnalysisPage.vue'),
      props: true,
    },
    {
      path: '/company',
      name: 'company',
      component: () => import('@/pages/CompanyProfilePage.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/pages/SettingsPage.vue'),
    },
  ],
})

export default router
