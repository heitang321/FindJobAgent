<script setup>
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const router = useRouter()

function handleLogout() {
  userStore.logout()
  router.replace('/login')
}
</script>

<template>
  <div class="app-shell">
    <nav class="nav-bar">
      <div class="nav-blur"></div>
      <div class="nav-content">
        <router-link to="/" class="nav-logo">
          <svg class="logo-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
            <path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" opacity="0.5"/>
          </svg>
          <span class="logo-text">FindJobAgent</span>
        </router-link>

        <div class="nav-menu" v-if="userStore.token">
          <router-link to="/" class="nav-link" active-class="active">首页</router-link>
          <router-link to="/history" class="nav-link" active-class="active">历史记录</router-link>
        </div>

        <div class="nav-right">
          <template v-if="userStore.token">
            <span class="nav-username">{{ userStore.userInfo?.username || '用户' }}</span>
            <button class="nav-logout" @click="handleLogout">退出</button>
          </template>
          <template v-else>
            <button class="nav-login-btn" @click="$router.push('/login')">登录</button>
          </template>
        </div>
      </div>
    </nav>

    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="route-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ===== Frosted glass navigation bar ===== */
.nav-bar {
  position: sticky;
  top: 0;
  z-index: 100;
  height: var(--header-height);
  overflow: hidden;
}

.nav-blur {
  position: absolute;
  inset: 0;
  background: rgba(251, 251, 253, 0.72);
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  border-bottom: 1px solid var(--apple-border);
  transition: background 0.3s var(--ease-smooth);
}

.nav-content {
  position: relative;
  height: 100%;
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

/* ===== Logo ===== */
.nav-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
}

.logo-icon {
  width: 28px;
  height: 28px;
  color: var(--apple-blue);
  transition: transform 0.4s var(--ease-spring);
}

.nav-logo:hover .logo-icon {
  transform: rotate(-8deg) scale(1.1);
}

.logo-text {
  font-size: 18px;
  font-weight: 600;
  color: var(--apple-gray-1);
  letter-spacing: -0.02em;
}

/* ===== Nav menu ===== */
.nav-menu {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  margin-left: 20px;
}

.nav-link {
  position: relative;
  padding: 6px 16px;
  font-size: 14px;
  color: var(--apple-gray-2);
  text-decoration: none;
  border-radius: 980px;
  transition: all 0.25s var(--ease-smooth);
}

.nav-link:hover {
  color: var(--apple-gray-1);
  background: rgba(0, 0, 0, 0.04);
}

.nav-link.active {
  color: var(--apple-blue);
  background: rgba(0, 113, 227, 0.08);
}

/* ===== Right section ===== */
.nav-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.nav-username {
  font-size: 13px;
  color: var(--apple-gray-3);
}

.nav-logout {
  background: none;
  border: none;
  font-size: 13px;
  color: var(--apple-gray-3);
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 980px;
  transition: all 0.2s var(--ease-smooth);
}

.nav-logout:hover {
  color: var(--apple-gray-1);
  background: rgba(0, 0, 0, 0.05);
}

.nav-login-btn {
  background: var(--apple-blue);
  color: #fff;
  border: none;
  padding: 6px 18px;
  font-size: 13px;
  border-radius: 980px;
  cursor: pointer;
  transition: all 0.3s var(--ease-spring);
}

.nav-login-btn:hover {
  background: var(--apple-blue-hover);
  transform: scale(1.04);
}

/* ===== Main content ===== */
.main-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
