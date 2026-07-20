import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getUserInfo, loginWithEmail, registerWithEmail } from '@/api'

export const useUserStore = defineStore('user', () => {
  // 用户信息
  const userInfo = ref(null)
  // 登录令牌
  const token = ref(localStorage.getItem('token') || '')

  // 设置登录令牌
  function setToken(newToken) {
    token.value = newToken
    if (newToken) {
      localStorage.setItem('token', newToken)
    } else {
      localStorage.removeItem('token')
    }
  }

  // 获取用户信息
  async function fetchUserInfo() {
    if (!token.value) return null
    try {
      const data = await getUserInfo()
      userInfo.value = data
      return data
    } catch {
      setToken('')
      userInfo.value = null
      return null
    }
  }

  async function login(payload) {
    const data = await loginWithEmail(payload)
    setToken(data.access_token)
    userInfo.value = data.user
    return data
  }

  async function register(payload) {
    const data = await registerWithEmail(payload)
    setToken(data.access_token)
    userInfo.value = data.user
    return data
  }

  // 登出
  function logout() {
    setToken('')
    userInfo.value = null
  }

  return {
    userInfo,
    token,
    setToken,
    fetchUserInfo,
    login,
    register,
    logout,
  }
})
