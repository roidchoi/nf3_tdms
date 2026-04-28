import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '@/views/DashboardView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView // [수정] HomeView 대신 연결
    },

    {
      path: '/schedules',
      name: 'schedules',
      component: () => import('@/views/ScheduleView.vue') // Lazy Load
    },
    
    { // [추가]
      path: '/health',
      name: 'health',
      component: () => import('@/views/HealthView.vue')
    },
    
    {
      path: '/explorer',
      name: 'explorer',
      component: () => import('@/views/DataExplorerView.vue')
    },

    { // [추가] API 진단 도구
      path: '/api-debugger',
      name: 'api-debugger',
      component: () => import('@/views/ApiDebuggerView.vue')
    }
  ],
})

export default router
