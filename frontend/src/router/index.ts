import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/dashboard' },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '仪表盘' },
  },
  {
    path: '/users',
    name: 'users',
    component: () => import('@/views/Users.vue'),
    meta: { title: '用户管理' },
  },
  {
    path: '/users/:id',
    name: 'user-detail',
    component: () => import('@/views/UserDetail.vue'),
    meta: { title: '用户详情' },
  },
  {
    path: '/items',
    name: 'items',
    component: () => import('@/views/Items.vue'),
    meta: { title: '商品管理' },
  },
  {
    path: '/items/:id',
    name: 'item-detail',
    component: () => import('@/views/ItemDetail.vue'),
    meta: { title: '商品详情' },
  },
  {
    path: '/analysis',
    name: 'analysis',
    component: () => import('@/views/Analysis.vue'),
    meta: { title: '深度分析' },
  },
  {
    path: '/recommendations',
    name: 'recommendations',
    component: () => import('@/views/Recommendations.vue'),
    meta: { title: '智能推荐' },
  },
  {
    path: '/models',
    name: 'models',
    component: () => import('@/views/Models.vue'),
    meta: { title: '预测模型' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

export default router
