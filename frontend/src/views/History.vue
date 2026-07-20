<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getResumeHistory } from '@/api'

const router = useRouter()
const tasks = ref([])
const loading = ref(false)

const stageConfig = {
  upload: { label: '待分析', color: '#86868b', bg: 'rgba(134, 134, 139, 0.1)' },
  analyzing: { label: '分析中', color: '#0071e3', bg: 'rgba(0, 113, 227, 0.1)' },
  job_input: { label: '待提交JD', color: '#af52de', bg: 'rgba(175, 82, 222, 0.1)' },
  job_analyzing: { label: 'JD分析中', color: '#af52de', bg: 'rgba(175, 82, 222, 0.1)' },
  ready_to_optimize: { label: '待优化', color: '#ff9500', bg: 'rgba(255, 149, 0, 0.1)' },
  optimizing: { label: '优化中', color: '#ff9500', bg: 'rgba(255, 149, 0, 0.1)' },
  done: { label: '已完成', color: '#34c759', bg: 'rgba(52, 199, 89, 0.1)' },
  error: { label: '失败', color: '#ff3b30', bg: 'rgba(255, 59, 48, 0.08)' },
}

function stageInfo(stage) {
  return stageConfig[stage] || { label: stage, color: '#86868b', bg: 'rgba(134, 134, 139, 0.1)' }
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
    <!-- Hero -->
    <section class="page-hero anim-fade-in">
      <p class="hero-eyebrow">History</p>
      <h1 class="hero-title anim-fade-up delay-1">简历任务历史</h1>
      <p class="hero-subtitle anim-fade-up delay-2">查看你所有上传的简历任务记录</p>
    </section>

    <!-- Action bar -->
    <div class="action-bar anim-fade-up delay-3">
      <span class="task-count" v-if="tasks.length">{{ tasks.length }} 条记录</span>
      <button class="new-btn" @click="startNew">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        上传新简历
      </button>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && tasks.length === 0" class="empty-state anim-scale-in">
      <div class="empty-icon-wrap">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M14 3v4a1 1 0 001 1h4" stroke="var(--apple-gray-5)" stroke-width="1.5" stroke-linecap="round"/>
          <path d="M17 21H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z" stroke="var(--apple-gray-5)" stroke-width="1.5" stroke-linejoin="round"/>
          <path d="M9 13h6M9 17h6" stroke="var(--apple-gray-5)" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>
      <h2 class="empty-title">还没有简历任务记录</h2>
      <p class="empty-desc">上传你的第一份简历，开始 AI 优化之旅</p>
      <button class="empty-action-btn" @click="startNew">立即上传</button>
    </div>

    <!-- Card grid -->
    <div v-else class="card-grid">
      <div
        v-for="(task, idx) in tasks"
        :key="task.task_id"
        class="task-card glass-card"
        :style="{ animationDelay: `${idx * 80}ms` }"
        @click="viewTask(task.task_id)"
      >
        <!-- Top row: status badge + match score -->
        <div class="card-top">
          <span
            class="status-badge"
            :style="{ color: stageInfo(task.current_stage).color, background: stageInfo(task.current_stage).bg }"
          >
            <span class="status-dot" :style="{ background: stageInfo(task.current_stage).color }"></span>
            {{ stageInfo(task.current_stage).label }}
          </span>
          <span v-if="task.match_score !== null && task.match_score !== undefined" class="match-score">
            {{ task.match_score }}<span class="match-suffix">/100</span>
          </span>
        </div>

        <!-- Main info -->
        <div class="card-body">
          <h3 class="card-title">{{ task.resume_name || `任务 ${task.task_id.slice(0, 8)}` }}</h3>
          <div class="card-meta">
            <span class="meta-chip">{{ task.file_type }}</span>
            <span v-if="task.has_optimized" class="meta-chip meta-chip--green">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M5 13l4 4L19 7" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              已优化
            </span>
          </div>
        </div>

        <!-- Footer -->
        <div class="card-footer">
          <span class="card-time">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
              <path d="M12 7v5l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            {{ formatTime(task.created_at) }}
          </span>
          <span class="card-action">
            查看
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M9 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.history-page {
  max-width: 1200px;
  margin: 0 auto;
  padding-bottom: 80px;
}

/* ===== Hero ===== */
.page-hero {
  text-align: center;
  padding: 80px 22px 40px;
}

.hero-eyebrow {
  font-size: 13px;
  font-weight: 600;
  color: var(--apple-blue);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 12px;
}

.hero-title {
  font-size: 48px;
  font-weight: 700;
  color: var(--apple-gray-1);
  letter-spacing: -0.03em;
  margin-bottom: 12px;
}

.hero-subtitle {
  font-size: 19px;
  color: var(--apple-gray-3);
}

/* ===== Action bar ===== */
.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 22px;
  margin-bottom: 28px;
}

.task-count {
  font-size: 14px;
  color: var(--apple-gray-4);
}

.new-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  background: var(--apple-blue);
  color: #fff;
  border: none;
  border-radius: 980px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s var(--ease-spring);
}

.new-btn:hover {
  background: var(--apple-blue-hover);
  transform: scale(1.04);
  box-shadow: 0 4px 16px rgba(0, 113, 227, 0.3);
}

/* ===== Empty state ===== */
.empty-state {
  text-align: center;
  padding: 80px 22px;
}

.empty-icon-wrap {
  margin-bottom: 20px;
  animation: float 3s var(--ease-smooth) infinite;
}

.empty-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--apple-gray-2);
  margin-bottom: 8px;
}

.empty-desc {
  font-size: 15px;
  color: var(--apple-gray-4);
  margin-bottom: 24px;
}

.empty-action-btn {
  padding: 10px 28px;
  background: var(--apple-blue);
  color: #fff;
  border: none;
  border-radius: 980px;
  font-size: 15px;
  cursor: pointer;
  transition: all 0.3s var(--ease-spring);
}

.empty-action-btn:hover {
  background: var(--apple-blue-hover);
  transform: scale(1.04);
}

/* ===== Card grid ===== */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
  padding: 0 22px;
}

.task-card {
  padding: 24px;
  border-radius: var(--apple-radius);
  cursor: pointer;
  animation: fadeUp 0.6s var(--ease-spring) both;
}

.task-card:hover {
  transform: translateY(-6px);
  box-shadow: var(--apple-shadow-lg);
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 980px;
  font-size: 12px;
  font-weight: 500;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.match-score {
  font-size: 20px;
  font-weight: 700;
  color: var(--apple-gray-1);
}

.match-suffix {
  font-size: 12px;
  color: var(--apple-gray-4);
  font-weight: 400;
}

.card-body {
  margin-bottom: 16px;
}

.card-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--apple-gray-1);
  margin-bottom: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-meta {
  display: flex;
  gap: 8px;
}

.meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 980px;
  font-size: 12px;
  background: var(--apple-gray-6);
  color: var(--apple-gray-3);
}

.meta-chip--green {
  background: rgba(52, 199, 89, 0.1);
  color: #248a3d;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 14px;
  border-top: 1px solid var(--apple-border);
}

.card-time {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: var(--apple-gray-4);
}

.card-action {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 14px;
  color: var(--apple-blue);
  font-weight: 500;
  transition: gap 0.3s var(--ease-spring);
}

.task-card:hover .card-action {
  gap: 6px;
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .hero-title { font-size: 32px; }
  .hero-subtitle { font-size: 16px; }
  .card-grid { grid-template-columns: 1fr; }
}
</style>
