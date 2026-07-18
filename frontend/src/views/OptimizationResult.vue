<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  downloadOptimizedResume,
  getOptimizationResult,
  triggerOptimization,
} from '@/api'

const route = useRoute()
const taskId = computed(() => String(route.params.taskId || ''))
const result = ref(null)
const loading = ref(false)
const triggering = ref(false)
let pollTimer = null

const sections = computed(() => result.value?.diff_report?.sections || [])
const summary = computed(() => result.value?.optimization_summary || {})
const isRunning = computed(() => result.value?.current_stage === 'optimizing')

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(loadResult, 1500)
}

async function loadResult() {
  if (!taskId.value) return
  loading.value = !result.value
  try {
    result.value = await getOptimizationResult(taskId.value)
    if (result.value.current_stage === 'optimizing') {
      if (!pollTimer) startPolling()
    } else {
      stopPolling()
    }
  } finally {
    loading.value = false
  }
}

async function startOptimization() {
  triggering.value = true
  try {
    await triggerOptimization(taskId.value)
    ElMessage.success('已启动简历优化')
    result.value = {
      task_id: taskId.value,
      current_stage: 'optimizing',
      diff_report: { sections: [] },
      optimization_summary: {},
    }
    startPolling()
  } finally {
    triggering.value = false
  }
}

async function downloadResume() {
  const blob = await downloadOptimizedResume(taskId.value)
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${taskId.value}_optimized_resume.docx`
  anchor.click()
  window.URL.revokeObjectURL(url)
}

function spanClass(type, side) {
  return {
    'diff-added': side === 'right' && type === 'added',
    'diff-removed': side === 'left' && type === 'removed',
    'diff-modified': type === 'modified',
  }
}

onMounted(loadResult)
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="optimization-page" v-loading="loading">
    <div class="page-header">
      <div>
        <h1>简历优化结果</h1>
        <p>任务 ID：{{ taskId }}</p>
      </div>
      <div class="actions">
        <el-tag v-if="result" :type="result.current_stage === 'done' ? 'success' : 'warning'">
          {{ result.current_stage }}
        </el-tag>
        <el-button type="primary" :loading="triggering || isRunning" @click="startOptimization">
          {{ isRunning ? '优化中…' : '重新优化' }}
        </el-button>
        <el-button
          type="success"
          :disabled="!result?.download_ready"
          @click="downloadResume"
        >
          下载 Word
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="result?.error"
      type="error"
      :title="result.error"
      show-icon
      :closable="false"
      class="error-alert"
    />

    <el-row v-if="result" :gutter="16" class="summary-row">
      <el-col :span="6">
        <el-statistic title="新增" :value="summary.added_count || 0" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="修改" :value="summary.modified_count || 0" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="删除" :value="summary.removed_count || 0" />
      </el-col>
      <el-col :span="6">
        <el-statistic title="优化段落" :value="summary.rewritten_sections?.length || 0" />
      </el-col>
    </el-row>

    <el-card v-if="summary.added_keywords?.length" class="keyword-card">
      <span class="card-label">新增岗位关键词：</span>
      <el-tag v-for="keyword in summary.added_keywords" :key="keyword" class="keyword-tag">
        {{ keyword }}
      </el-tag>
    </el-card>

    <div v-if="sections.length" class="comparison-list">
      <el-card
        v-for="section in sections"
        :key="`${section.section_type}-${section.section_index}`"
        class="section-card"
      >
        <template #header>
          <div class="section-header">
            <strong>{{ section.section_type }} #{{ section.section_index + 1 }}</strong>
            <el-tag :type="section.changed ? 'warning' : 'info'">
              {{ section.changed ? '已修改' : '保持不变' }}
            </el-tag>
          </div>
        </template>

        <el-row :gutter="20">
          <el-col :span="12">
            <h3>原文</h3>
            <div class="diff-panel original-panel">
              <template v-for="(span, index) in section.spans" :key="index">
                <span :class="spanClass(span.type, 'left')">{{ span.original_text }}</span>
              </template>
            </div>
          </el-col>
          <el-col :span="12">
            <h3>优化后</h3>
            <div class="diff-panel optimized-panel">
              <template v-for="(span, index) in section.spans" :key="index">
                <span :class="spanClass(span.type, 'right')">{{ span.optimized_text }}</span>
              </template>
            </div>
          </el-col>
        </el-row>

        <div v-if="section.change_reason" class="change-reason">
          <strong>修改说明：</strong>{{ section.change_reason }}
        </div>
        <div v-if="section.changes?.length" class="change-list">
          <el-tag
            v-for="(change, index) in section.changes"
            :key="index"
            :type="change.type === 'added' ? 'success' : change.type === 'removed' ? 'danger' : 'warning'"
          >
            {{ change.description }}
          </el-tag>
        </div>
      </el-card>
    </div>

    <el-empty v-else-if="result && !isRunning" description="暂无优化对比数据" />
  </div>
</template>

<style scoped>
.optimization-page {
  max-width: 1280px;
  margin: 0 auto;
  padding: 28px;
}

.page-header,
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-header p {
  margin-top: 8px;
  color: #909399;
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.error-alert,
.summary-row,
.keyword-card,
.section-card {
  margin-top: 20px;
}

.summary-row .el-col {
  padding: 18px;
  background: #fff;
  border-radius: 8px;
}

.keyword-tag,
.change-list .el-tag {
  margin: 4px;
}

.card-label {
  font-weight: 600;
}

.diff-panel {
  min-height: 110px;
  padding: 16px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.7;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
}

.original-panel {
  background: #fafafa;
}

.optimized-panel {
  background: #f7fff8;
}

.diff-added {
  background: #d9f7be;
}

.diff-removed {
  color: #c45656;
  text-decoration: line-through;
  background: #fde2e2;
}

.diff-modified {
  background: #faecd8;
}

.change-reason {
  margin-top: 16px;
  padding: 12px;
  color: #606266;
  background: #f5f7fa;
  border-radius: 6px;
}

.change-list {
  margin-top: 10px;
}
</style>
