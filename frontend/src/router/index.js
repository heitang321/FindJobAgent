import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/DefaultLayout.vue'),
    children: [
      {
        path: '',
        name: 'Home',
        component: () => import('@/views/Home.vue'),
        meta: { title: '首页' },
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
        meta: { title: '简历优化结果' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局前置守卫：设置页面标题
router.beforeEach((to, _from, next) => {
  const title = to.meta.title
  if (title) {
    document.title = `${title} - FindJobAgent`
  }
  next()
})

export default router
