<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload as UploadIcon, Loading } from '@element-plus/icons-vue'
import { useWorkflowStore } from '@/stores/workflow'
import { checkHealth } from '@/api'
import request from '@/api/request'

const wf = useWorkflowStore()
const healthStatus = ref('检测中...')
const jdUrl = ref('')

const stage = computed(() => wf.stage)
const isRunning = computed(() => wf.isRunning)

const showUpload = computed(() => ['idle', 'uploading'].includes(stage.value))
const showResumeResult = computed(() => !!wf.structuredResume)
const showJdInput = computed(() =>
  ['job_input', 'job_analyzing', 'ready_to_optimize', 'optimizing', 'done'].includes(stage.value)
    || (stage.value === 'error' && !!wf.structuredResume),
)
const showMatchResult = computed(() => !!wf.matchResult)
const showOptimizeButton = computed(() =>
  ['ready_to_optimize', 'optimizing', 'done'].includes(stage.value)
    || (stage.value === 'error' && !!wf.jobRequirements && !!wf.gapReport),
)
const showOptimizeResult = computed(() =>
  stage.value === 'done' && Boolean(wf.diffReport?.sections?.length),
)

async function handleUpload(file) {
  const f = file?.raw !== undefined ? file.raw : file
  try {
    await wf.upload(f)
    ElMessage.success('简历已上传，正在分析...')
  } catch (e) {}
  return false
}

async function submitJd() {
  if (!jdUrl.value.trim()) { ElMessage.warning('请输入 JD URL'); return }
  try {
    await wf.submitJob(jdUrl.value.trim())
    ElMessage.success('岗位分析完成')
  } catch (e) {}
}

async function startOptimize() {
  try {
    await wf.optimize()
    ElMessage.success('优化任务已启动')
  } catch (e) {}
}

async function download() {
  const blob = await request.get(`/optimize/${wf.taskId}/download`, { responseType: 'blob' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `optimized_resume_${(wf.taskId || 'task').slice(0, 8)}.docx`
  a.click()
  window.URL.revokeObjectURL(url)
}

function reset() { jdUrl.value = ''; wf.reset() }

async function checkApi() {
  try {
    const data = await checkHealth()
    healthStatus.value = data.status === 'ok' ? 'API 正常' : '异常'
  } catch { healthStatus.value = 'API 不可用' }
}

onMounted(checkApi)
</script>

<template>
  <div class="home">
    <div class="hero">
      <h1>简历优化智能助手</h1>
      <p>上传简历 + 提供岗位 JD URL，AI 帮你针对性优化</p>
      <p class="health">后端状态: {{ healthStatus }}</p>
    </div>
    <el-card class="pipeline-card">
      <el-alert
        v-if="wf.error"
        type="error"
        title="任务执行失败"
        :description="wf.error"
        show-icon
        :closable="false"
        class="workflow-error"
      />
      <div class="step">
        <div class="step-header">
          <el-tag type="primary" round>步骤 1</el-tag>
          <h3>上传简历</h3>
        </div>
        <el-upload
          v-if="showUpload"
          drag
          accept=".pdf,.docx,.doc"
          :auto-upload="true"
          :show-file-list="false"
          :before-upload="handleUpload"
          :disabled="isRunning"
        >
          <el-icon class="el-icon--upload"><UploadIcon /></el-icon>
          <div class="el-upload__text">拖拽文件到此处或 <em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">支持 PDF / DOCX / DOC，仅本地分析</div>
          </template>
        </el-upload>
        <div v-if="stage === 'uploading'" class="loading-hint">
          <el-icon class="is-loading"><Loading /></el-icon> 正在上传...
        </div>
        <div v-if="stage === 'job_input' && !wf.structuredResume" class="loading-hint">
          <el-icon class="is-loading"><Loading /></el-icon>
          Agent 1 正在后台结构化简历（约 10-20s），你可以同时输入 JD URL ↓
        </div>
      </div>

      <div v-if="showResumeResult" class="step">
        <div class="step-header">
          <el-tag type="success" round>Agent 1 完成</el-tag>
          <h3>简历分析结果</h3>
        </div>
        <div class="resume-summary">
          <p><strong>姓名：</strong>{{ wf.structuredResume?.basic_info?.name || '-' }}</p>
          <p>
            <strong>技能：</strong>
            <el-tag v-for="s in wf.structuredResume?.skills || []" :key="s" class="skill-tag">{{ s }}</el-tag>
          </p>
          <p>
            <strong>工作经历：</strong>{{ wf.structuredResume?.work_experience?.length || 0 }} 条 ｜
            <strong>项目经历：</strong>{{ wf.structuredResume?.project_experience?.length || 0 }} 条
          </p>
        </div>
      </div>
      <!-- MORE_STEPS_PLACEHOLDER -->
      <div v-if="showJdInput" class="step">
        <div class="step-header">
          <el-tag type="primary" round>步骤 2</el-tag>
          <h3>提交岗位 JD URL</h3>
        </div>
        <el-input
          v-model="jdUrl"
          placeholder="https://www.zhaopin.com/jobdetail/CC....htm"
          clearable
          :disabled="stage === 'job_analyzing'"
        >
          <template #append>
            <el-button
              type="primary"
              :loading="stage === 'job_analyzing'"
              :disabled="!jdUrl.trim()"
              @click="submitJd"
            >
              {{ stage === 'job_analyzing' ? '分析中' : '提交分析' }}
            </el-button>
          </template>
        </el-input>
        <div v-if="stage === 'job_analyzing'" class="loading-hint">
          <el-icon class="is-loading"><Loading /></el-icon>
          Agent 2 正在抓取 JD + 结构化 + 匹配分析（约 30-60s）...
        </div>
      </div>

      <div v-if="showMatchResult" class="step">
        <div class="step-header">
          <el-tag type="success" round>Agent 2 完成</el-tag>
          <h3>岗位匹配结果</h3>
        </div>
        <el-row :gutter="16">
          <el-col :span="6">
            <el-statistic title="匹配度" :value="wf.matchScore" suffix="/100" />
          </el-col>
          <el-col :span="9">
            <div class="match-block">
              <strong>已匹配技能</strong>
              <div>
                <el-tag v-for="s in wf.matchResult?.matched_skills || []" :key="s" type="success" class="skill-tag">{{ s }}</el-tag>
              </div>
            </div>
          </el-col>
          <el-col :span="9">
            <div class="match-block">
              <strong>缺失技能</strong>
              <div>
                <el-tag v-for="s in wf.matchResult?.missing_skills || []" :key="s" type="danger" class="skill-tag">{{ s }}</el-tag>
              </div>
            </div>
          </el-col>
        </el-row>
      </div>
      <!-- FINAL_STEPS_PLACEHOLDER -->
      <div v-if="showOptimizeButton" class="step">
        <div class="step-header">
          <el-tag type="primary" round>步骤 3</el-tag>
          <h3>触发简历优化</h3>
        </div>
        <el-button
          type="primary"
          size="large"
          :loading="stage === 'optimizing'"
          :disabled="stage === 'optimizing'"
          @click="startOptimize"
        >
          {{ stage === 'optimizing' ? '优化中（约 30-60s）...' : '开始优化简历' }}
        </el-button>
        <div v-if="stage === 'optimizing'" class="loading-hint">
          <el-icon class="is-loading"><Loading /></el-icon>
          Agent 3 正在改写 sections + 生成 DOCX...
        </div>
      </div>

      <div v-if="showOptimizeResult" class="step">
        <div class="step-header">
          <el-tag type="success" round>Agent 3 完成</el-tag>
          <h3>优化结果</h3>
          <el-button type="success" @click="download" :disabled="!wf.downloadReady">下载 Word</el-button>
        </div>
        <el-row :gutter="16" class="summary-row">
          <el-col :span="6"><el-statistic title="新增" :value="wf.optimizationSummary?.added_count || 0" /></el-col>
          <el-col :span="6"><el-statistic title="修改" :value="wf.optimizationSummary?.modified_count || 0" /></el-col>
          <el-col :span="6"><el-statistic title="优化段落" :value="wf.optimizationSummary?.rewritten_sections?.length || 0" /></el-col>
          <el-col :span="6"><el-statistic title="新增关键词" :value="wf.optimizationSummary?.added_keywords?.length || 0" /></el-col>
        </el-row>
        <div v-if="wf.optimizationSummary?.added_keywords?.length" class="keyword-card">
          <span class="card-label">新增岗位关键词：</span>
          <el-tag v-for="kw in wf.optimizationSummary.added_keywords" :key="kw" class="skill-tag">{{ kw }}</el-tag>
        </div>
        <div v-if="wf.diffReport?.sections?.length" class="diff-list">
          <el-card
            v-for="section in wf.diffReport.sections"
            :key="`${section.section_type}-${section.section_index}`"
            class="section-card"
          >
            <template #header>
              <div class="step-header">
                <strong>{{ section.section_type }} #{{ section.section_index + 1 }}</strong>
                <el-tag :type="section.changed ? 'warning' : 'info'">
                  {{ section.changed ? '已修改' : '保持不变' }}
                </el-tag>
              </div>
            </template>
            <el-row :gutter="20">
              <el-col :span="12">
                <h3>原文</h3>
                <div class="diff-panel original-panel">{{ section.original_content }}</div>
              </el-col>
              <el-col :span="12">
                <h3>优化后</h3>
                <div class="diff-panel optimized-panel">{{ section.optimized_content }}</div>
              </el-col>
            </el-row>
            <div v-if="section.change_reason" class="change-reason">
              <strong>修改说明：</strong>{{ section.change_reason }}
            </div>
          </el-card>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.home { max-width: 1280px; margin: 0 auto; padding: 28px; }
.hero { text-align: center; margin-bottom: 28px; }
.hero h1 { font-size: 32px; color: #303133; margin: 0 0 8px; }
.hero p { color: #909399; margin: 4px 0; }
.health { font-size: 13px; margin-top: 12px; }
.pipeline-card { padding: 8px 16px; }
.workflow-error { margin: 8px 0 18px; }

.step { padding: 18px 0; border-bottom: 1px dashed #ebeef5; }
.step:last-child { border-bottom: none; }
.step-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.step-header h3 { margin: 0; font-size: 18px; color: #303133; flex: 1; }

.loading-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #909399;
  margin-top: 12px;
}

.resume-summary p { margin: 8px 0; line-height: 1.8; }
.skill-tag { margin: 2px 4px 2px 0; }

.match-block strong { display: block; margin-bottom: 8px; color: #606266; }

.summary-row { margin-top: 12px; }
.summary-row .el-col {
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
}

.keyword-card {
  margin-top: 16px;
  padding: 12px 16px;
  background: #f7fff8;
  border-radius: 6px;
}
.card-label { font-weight: 600; margin-right: 8px; }

.diff-list { margin-top: 20px; }
.section-card { margin-bottom: 16px; }
.diff-panel {
  min-height: 110px;
  padding: 16px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.7;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
}
.original-panel { background: #fafafa; }
.optimized-panel { background: #f7fff8; }
.change-reason {
  margin-top: 16px;
  padding: 12px;
  color: #606266;
  background: #f5f7fa;
  border-radius: 6px;
}
</style>
