<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check } from '@element-plus/icons-vue'
import { getResumeHistory } from '@/api'

const router = useRouter()
const tasks = ref([])
const loading = ref(false)

const stageTagType = (stage) => {
  if (stage === 'done') return 'success'
  if (stage === 'error') return 'danger'
  if (['upload', 'analyzing', 'job_analyzing', 'optimizing'].includes(stage)) return 'warning'
  return 'info'
}

const stageLabel = (stage) => {
  const labels = {
    upload: '待分析',
    analyzing: '分析中',
    job_input: '待提交JD',
    job_analyzing: 'JD分析中',
    ready_to_optimize: '待优化',
    optimizing: '优化中',
    done: '已完成',
    error: '失败',
  }
  return labels[stage] || stage
}

function formatTime(iso) {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

function viewTask(taskId) {
  router.push({ name: 'OptimizationResult', params: { taskId } })
}

function startNew() {
  router.push({ name: 'Home' })
}

async function loadHistory() {
  loading.value = true
  try {
    const data = await getResumeHistory()
    tasks.value = data.tasks || []
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message || '获取历史记录失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadHistory)
</script>

<template>
  <div class="history-page" v-loading="loading">
    <div class="page-header">
      <div>
        <h1>简历任务历史</h1>
        <p>查看你所有上传的简历任务记录</p>
      </div>
      <el-button type="primary" @click="startNew">上传新简历</el-button>
    </div>

    <el-empty v-if="!loading && tasks.length === 0" description="还没有简历任务记录">
      <el-button type="primary" @click="startNew">立即上传</el-button>
    </el-empty>

    <el-table
      v-else
      :data="tasks"
      stripe
      style="width: 100%"
      @row-click="(row) => viewTask(row.task_id)"
    >
      <el-table-column label="简历" min-width="140">
        <template #default="{ row }">
          <span>{{ row.resume_name || `任务 ${row.task_id.slice(0, 8)}` }}</span>
        </template>
      </el-table-column>
      <el-table-column label="文件类型" width="100">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.file_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="stageTagType(row.current_stage)" size="small">
            {{ stageLabel(row.current_stage) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="匹配度" width="100" align="center">
        <template #default="{ row }">
          <span v-if="row.match_score !== null && row.match_score !== undefined">
            {{ row.match_score }} / 100
          </span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="已优化" width="80" align="center">
        <template #default="{ row }">
          <el-icon v-if="row.has_optimized" color="#67c23a" size="18"><Check /></el-icon>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click.stop="viewTask(row.task_id)">
            查看
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.history-page {
  max-width: 1280px;
  margin: 0 auto;
  padding: 28px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 28px;
  color: #303133;
  margin: 0 0 6px;
}

.page-header p {
  color: #909399;
  margin: 0;
}

.text-muted {
  color: #c0c4cc;
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>
