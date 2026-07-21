import axios from 'axios'
import { useUserStore } from '@/stores/user'
import { ElMessage } from 'element-plus'
import 'element-plus/es/components/message/style/css'

const request = axios.create({
  // 通过 Vite 代理转发请求，开发环境直接用相对路径
  baseURL: '/api/v1',
  // Agent 2 同步执行（LLM × 2 + CDP 抓取）可能 60-90s，给到 3 分钟
  timeout: 180000,
})

// 请求拦截器：自动携带登录令牌
request.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()
    if (userStore.token) {
      config.headers.Authorization = `Bearer ${userStore.token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器：统一处理错误
request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.detail || error.message || '请求失败'
    ElMessage.error(message)
    error.__messageShown = true

    const url = error.config?.url || ''
    const isAuthFormRequest = url.includes('/auth/login') || url.includes('/auth/register')

    // 401 未授权：业务接口登录令牌失效才跳转；登录表单自身的 401 要留在当前页展示错误。
    if (error.response?.status === 401 && !isAuthFormRequest) {
      const userStore = useUserStore()
      userStore.logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export default request
