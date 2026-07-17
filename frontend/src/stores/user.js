import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getUserInfo } from '@/api'

export const useUserStore = defineStore('user', () => {
  // 用户信息
  const userInfo = ref(null)
  // token
  const token = ref(localStorage.getItem('token') || '')

  // 设置 token
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
    } catch (error) {
      setToken('')
      userInfo.value = null
      return null
    }
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
    logout,
  }
})
