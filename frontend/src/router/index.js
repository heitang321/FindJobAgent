import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    children: [
      {
        path: '',
        name: 'Home',
        component: () => import('@/views/Home.vue'),
        meta: { title: '首页', requiresAuth: true },
      },
      {
        path: 'history',
        name: 'History',
        component: () => import('@/views/History.vue'),
        meta: { title: '历史记录', requiresAuth: true },
      },
      {
        path: 'login',
        name: 'Login',
        component: () => import('@/views/Login.vue'),
        meta: { title: '登录' },
      },
      {
        path: 'optimize/:taskId',
        name: 'OptimizationResult',
        component: () => import('@/views/OptimizationResult.vue'),
        meta: { title: '简历优化结果', requiresAuth: true },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局前置守卫：设置页面标题与登录态跳转
router.beforeEach(async (to, _from, next) => {
  const title = to.meta.title
  if (title) {
    document.title = `${title} - FindJobAgent`
  }

  const userStore = useUserStore()
  if (to.meta.requiresAuth && !userStore.token) {
    next({ name: 'Login' })
    return
  }
  if (to.meta.requiresAuth && userStore.token && !userStore.userInfo) {
    const user = await userStore.fetchUserInfo()
    if (!user) {
      next({ name: 'Login' })
      return
    }
  }
  if (to.name === 'Login' && userStore.token) {
    const user = userStore.userInfo || await userStore.fetchUserInfo()
    if (user) {
      next({ name: 'Home' })
      return
    }
  }
  next()
})

export default router
