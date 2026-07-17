<script setup>
import { ref, onMounted } from 'vue'
import { checkHealth } from '@/api'

const healthStatus = ref('检测中...')

async function checkApi() {
  try {
    const data = await checkHealth()
    healthStatus.value = data.status === 'ok' ? 'API 正常' : '异常'
  } catch {
    healthStatus.value = 'API 不可用'
  }
}

onMounted(() => checkApi())
</script>

<template>
  <div class="home">
    <el-row justify="center" align="middle" class="hero">
      <el-col :span="12" class="hero-content">
        <h1>简历优化智能助手</h1>
        <p>AI 驱动的简历分析与优化平台</p>
        <el-button type="primary" size="large">开始使用</el-button>
        <p class="health">后端状态: {{ healthStatus }}</p>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.home {
  height: 100%;
}

.hero {
  height: 100%;
  text-align: center;
}

.hero-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.hero-content h1 {
  font-size: 36px;
  color: #303133;
}

.hero-content p {
  color: #909399;
  font-size: 18px;
}

.health {
  margin-top: 20px;
  font-size: 14px;
  color: #909399;
}
</style>
