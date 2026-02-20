import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/pages/DashboardPage.vue'),
    },
    {
      path: '/company',
      name: 'company',
      component: () => import('@/pages/CompanyProfilePage.vue'),
    },
    {
      path: '/tenders',
      name: 'tenders',
      component: () => import('@/pages/TenderListPage.vue'),
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
  ],
})

export default router
