<script setup>
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
</script>

<template>
  <el-container class="layout-container">
    <el-header class="header">
      <div class="logo">FindJobAgent</div>
      <div class="header-right">
        <template v-if="userStore.token">
          <span class="username">{{ userStore.userInfo?.username || '用户' }}</span>
          <el-button type="text" @click="userStore.logout()">退出</el-button>
        </template>
        <template v-else>
          <el-button type="primary" @click="$router.push('/login')">登录</el-button>
        </template>
      </div>
    </el-header>

    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.layout-container {
  height: 100vh;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: #fff;
  border-bottom: 1px solid #e4e7ed;
  height: var(--header-height);
}

.logo {
  font-size: 20px;
  font-weight: bold;
  color: var(--el-color-primary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.username {
  color: #606266;
}

.main {
  background-color: #f5f7fa;
  padding: 0;
}
</style>
