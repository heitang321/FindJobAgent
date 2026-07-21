<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload as UploadIcon, Loading, Search } from '@element-plus/icons-vue'
import { useWorkflowStore } from '@/stores/workflow'
import { checkHealth } from '@/api'
import request from '@/api/request'
import JobCard from '@/components/JobCard.vue'

const wf = useWorkflowStore()
const healthStatus = ref('检测中...')
const jdUrl = ref('')

// ===== 鼠标视差 =====
const parallaxX = ref(0)
const parallaxY = ref(0)

function handleMouseMove(e) {
  const cx = window.innerWidth / 2
  const cy = window.innerHeight / 2
  parallaxX.value = (e.clientX - cx) / cx
  parallaxY.value = (e.clientY - cy) / cy
}

// ===== 功能卡片 =====
const features = [
  { icon: '📄', title: '智能解析', desc: '上传 PDF/DOCX，AI 自动结构化提取简历信息', color: '#0071e3' },
  { icon: '🎯', title: '精准匹配', desc: '对比岗位 JD，量化匹配度并识别缺失技能', color: '#af52de' },
  { icon: '✨', title: '一键优化', desc: 'AI 改写简历段落，生成可下载 Word 文档', color: '#34c759' },
]
const hoveredFeature = ref(-1)

// ===== 统计数字 =====
const stats = [
  { value: 3, suffix: ' 步', label: '极简流程' },
  { value: 100, suffix: '%', label: '本地处理' },
  { value: 10, suffix: 's', label: '平均解析' },
  { value: 0, suffix: '', label: '数据泄露' },
]
const animatedStats = ref(stats.map(() => 0))

function animateStats() {
  stats.forEach((s, i) => {
    const duration = 1200
    const start = performance.now()
    function tick(now) {
      const t = Math.min((now - start) / duration, 1)
      const eased = 1 - Math.pow(1 - t, 3)
      animatedStats.value[i] = Math.round(s.value * eased)
      if (t < 1) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })
}

// ===== 流程步骤 =====
const steps = [
  { num: '01', title: '上传简历', desc: '拖拽文件到上传区，支持 PDF / DOCX' },
  { num: '02', title: '提交 JD', desc: '粘贴招聘链接，AI 自动抓取分析' },
  { num: '03', title: '下载优化版', desc: 'AI 改写 + 一键下载 Word 文档' },
]
const activeStep = ref(0)
let stepTimer = null

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
  } catch {}
  return false
}

async function submitJd() {
  if (!jdUrl.value.trim()) { ElMessage.warning('请输入 JD URL'); return }
  try {
    await wf.submitJob(jdUrl.value.trim())
    ElMessage.success('岗位分析完成')
  } catch {}
}

// 自动推荐岗位：调后端 /job/{taskId}/search，用简历 skills 推导关键词
async function handleSearchJobs() {
  try {
    await wf.searchJobs()
    ElMessage.success(`已检索到 ${wf.jobSearchResults.length} 个岗位，请选择一个`)
  } catch {}
}

// 选中岗位卡片：自动填 URL 到输入框，用户可继续点"提交分析"
function handleSelectCard(card) {
  wf.selectJobCard(card)
  jdUrl.value = card.url
  ElMessage.success(`已选择：${card.title}，URL 已填入，可点"提交分析"继续`)
}

async function startOptimize() {
  try {
    await wf.optimize()
    ElMessage.success('优化任务已启动')
  } catch {}
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

onMounted(() => {
  checkApi()
  animateStats()
  stepTimer = setInterval(() => {
    activeStep.value = (activeStep.value + 1) % steps.length
  }, 2500)
})

onUnmounted(() => { if (stepTimer) clearInterval(stepTimer) })
</script>

<template>
  <div class="home" @mousemove="handleMouseMove">
    <!-- ===== 浮动背景光球 ===== -->
    <div class="bg-orbs">
      <div
        class="orb orb--1"
        :style="{ transform: `translate(${parallaxX * 30}px, ${parallaxY * 30}px)` }"
      ></div>
      <div
        class="orb orb--2"
        :style="{ transform: `translate(${parallaxX * -20}px, ${parallaxY * -25}px)` }"
      ></div>
      <div
        class="orb orb--3"
        :style="{ transform: `translate(${parallaxX * 15}px, ${parallaxY * -15}px)` }"
      ></div>
    </div>

    <!-- ===== Hero ===== -->
    <section class="hero">
      <div class="hero-content">
        <p class="hero-eyebrow anim-fade-in">FindJobAgent</p>
        <h1 class="hero-title anim-fade-up delay-1">
          简历优化<span class="gradient-text-blue">智能助手</span>
        </h1>
        <p class="hero-subtitle anim-fade-up delay-2">
          上传简历，提供岗位 JD，AI 帮你针对性优化。
        </p>
        <div class="hero-meta anim-fade-up delay-3">
          <span class="status-dot" :class="{ ok: healthStatus === 'API 正常' }"></span>
          <span class="health-text">{{ healthStatus }}</span>
        </div>
      </div>
      <div class="hero-bg"></div>
    </section>

    <!-- ===== 功能亮点 ===== -->
    <section class="features" v-if="showUpload">
      <div class="features-grid">
        <div
          v-for="(f, i) in features"
          :key="f.title"
          class="feature-card glass-card"
          v-reveal="{ delay: i * 120 }"
          @mouseenter="hoveredFeature = i"
          @mouseleave="hoveredFeature = -1"
        >
          <div class="feature-icon" :style="{ background: `${f.color}15`, color: f.color }">
            {{ f.icon }}
          </div>
          <h3 class="feature-title">{{ f.title }}</h3>
          <p class="feature-desc">{{ f.desc }}</p>
          <div class="feature-bar" :style="{
            background: f.color,
            transform: hoveredFeature === i ? 'scaleX(1)' : 'scaleX(0)'
          }"></div>
        </div>
      </div>
    </section>

    <!-- ===== 使用流程 ===== -->
    <section class="how-it-works" v-if="showUpload">
      <h2 class="section-heading anim-fade-up" v-reveal>三步搞定</h2>
      <p class="section-sub anim-fade-up delay-1" v-reveal="{ delay: 100 }">从上传到下载，不到两分钟</p>
      <div class="steps-track">
        <div class="steps-line"></div>
        <div
          v-for="(s, i) in steps"
          :key="s.num"
          class="step-node"
          :class="{ active: activeStep === i, done: showUpload === false || i < activeStep }"
          @mouseenter="activeStep = i"
          v-reveal="{ delay: i * 150 }"
        >
          <div class="step-circle">{{ s.num }}</div>
          <div class="step-info">
            <span class="step-name">{{ s.title }}</span>
            <span class="step-desc">{{ s.desc }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 统计带 ===== -->
    <section class="stats-band" v-if="showUpload" v-reveal>
      <div
        v-for="(s, i) in stats"
        :key="s.label"
        class="stats-item"
      >
        <span class="stats-num">
          {{ animatedStats[i] }}<span class="stats-suffix">{{ s.suffix }}</span>
        </span>
        <span class="stats-label">{{ s.label }}</span>
      </div>
    </section>

    <!-- ===== Pipeline ===== -->
    <section class="pipeline">
      <div v-if="wf.error" class="error-banner anim-scale-in">
        <strong>任务执行失败</strong>
        <span>{{ wf.error }}</span>
      </div>

      <!-- Step 1: Upload -->
      <div v-if="showUpload" class="step-section anim-fade-up">
        <div class="step-badge step-badge--1">01</div>
        <h2 class="step-title">上传简历</h2>
        <el-upload
          drag
          accept=".pdf,.docx,.doc"
          :auto-upload="true"
          :show-file-list="false"
          :before-upload="handleUpload"
          :disabled="isRunning"
          class="apple-upload"
        >
          <div class="upload-icon-wrap">
            <el-icon class="el-icon--upload"><UploadIcon /></el-icon>
          </div>
          <div class="upload-text">拖拽文件到此处或 <em>点击上传</em></div>
          <div class="upload-hint">支持 PDF / DOCX / DOC，仅本地分析</div>
        </el-upload>
        <div v-if="stage === 'uploading'" class="loading-pill">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>正在上传...</span>
        </div>
        <div v-if="stage === 'analyzing'" class="loading-pill">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>Agent 1 正在结构化简历（约 10-20s）...</span>
        </div>
      </div>

      <!-- Agent 1 Result -->
      <div v-if="showResumeResult" class="step-section glass-card step-card" v-reveal>
        <div class="step-badge step-badge--done">✓</div>
        <h2 class="step-title">简历分析结果</h2>
        <div class="resume-summary">
          <div class="summary-item">
            <span class="summary-label">姓名</span>
            <span class="summary-value">{{ wf.structuredResume?.basic_info?.name || '-' }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">技能</span>
            <div class="summary-tags">
              <span v-for="s in wf.structuredResume?.skills || []" :key="s" class="pill-tag">{{ s }}</span>
            </div>
          </div>
          <div class="summary-item">
            <span class="summary-label">经历</span>
            <span class="summary-value">
              工作 {{ wf.structuredResume?.work_experience?.length || 0 }} 条
              · 项目 {{ wf.structuredResume?.project_experience?.length || 0 }} 条
            </span>
          </div>
        </div>
      </div>

      <!-- Step 2: JD Input + Auto Search -->
      <div v-if="showJdInput" class="step-section anim-fade-up">
        <div class="step-badge step-badge--2">02</div>
        <h2 class="step-title">提交岗位 JD URL</h2>

        <!-- 手动输入 JD URL -->
        <div class="jd-input-wrap">
          <input
            v-model="jdUrl"
            type="text"
            class="jd-input"
            placeholder="https://www.zhaopin.com/jobdetail/CC....htm"
            :disabled="stage === 'job_analyzing'"
          />
          <button
            class="jd-submit-btn"
            :disabled="!jdUrl.trim() || stage === 'job_analyzing'"
            @click="submitJd"
          >
            <span v-if="stage === 'job_analyzing'" class="btn-loading">
              <el-icon class="is-loading"><Loading /></el-icon> 分析中
            </span>
            <span v-else>提交分析</span>
          </button>
        </div>

        <!-- 分隔线 -->
        <div class="jd-divider">
          <span class="jd-divider-text">或</span>
        </div>

        <!-- 自动推荐按钮 -->
        <button
          class="auto-search-btn"
          :disabled="wf.searchingJobs || stage === 'job_analyzing'"
          @click="handleSearchJobs"
        >
          <span v-if="wf.searchingJobs" class="btn-loading">
            <el-icon class="is-loading"><Loading /></el-icon> 正在检索岗位...
          </span>
          <span v-else>
            <el-icon class="auto-search-icon"><Search /></el-icon>
            根据简历自动推荐岗位
          </span>
        </button>

        <!-- 岗位卡片网格 -->
        <div v-if="wf.hasSearchResults" class="job-cards-grid">
          <div class="job-cards-header">
            <span class="job-cards-count">找到 {{ wf.jobSearchResults.length }} 个岗位</span>
            <span v-if="wf.searchKeywords" class="job-cards-keywords">关键词：{{ wf.searchKeywords }}</span>
          </div>
          <div class="job-cards-list">
            <JobCard
              v-for="card in wf.jobSearchResults"
              :key="card.url"
              :job="card"
              :selected="wf.selectedJobCard?.url === card.url"
              @select="handleSelectCard"
            />
          </div>
        </div>

        <!-- 分析中状态 -->
        <div v-if="stage === 'job_analyzing'" class="loading-pill">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>Agent 2 正在抓取 JD + 结构化 + 匹配分析（约 30-60s）...</span>
        </div>
      </div>

      <!-- Agent 2 Result -->
      <div v-if="showMatchResult" class="step-section glass-card step-card" v-reveal>
        <div class="step-badge step-badge--done">✓</div>
        <h2 class="step-title">岗位匹配结果</h2>
        <div class="match-grid">
          <div class="match-score-block">
            <div class="match-score-ring">
              <span class="score-value">{{ wf.matchScore ?? '-' }}</span>
              <span class="score-suffix">/100</span>
            </div>
            <span class="score-label">匹配度</span>
          </div>
          <div class="match-tags-block">
            <span class="block-label">已匹配技能</span>
            <div class="tag-list">
              <span v-for="s in wf.matchResult?.matched_skills || []" :key="s" class="pill-tag pill-tag--success">{{ s }}</span>
            </div>
          </div>
          <div class="match-tags-block">
            <span class="block-label">缺失技能</span>
            <div class="tag-list">
              <span v-for="s in wf.matchResult?.missing_skills || []" :key="s" class="pill-tag pill-tag--danger">{{ s }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 3: Optimize -->
      <div v-if="showOptimizeButton" class="step-section anim-fade-up">
        <div class="step-badge step-badge--3">03</div>
        <h2 class="step-title">触发简历优化</h2>
        <button
          class="optimize-btn"
          :disabled="stage === 'optimizing'"
          @click="startOptimize"
        >
          <span v-if="stage === 'optimizing'" class="btn-loading">
            <el-icon class="is-loading"><Loading /></el-icon> 优化中（约 30-60s）...
          </span>
          <span v-else>开始优化简历</span>
        </button>
        <div v-if="stage === 'optimizing'" class="loading-pill">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>Agent 3 正在改写 sections + 生成 DOCX...</span>
        </div>
      </div>

      <!-- Agent 3 Result -->
      <div v-if="showOptimizeResult" class="step-section" v-reveal>
        <div class="result-header">
          <div class="step-badge step-badge--done">✓</div>
          <h2 class="step-title">优化结果</h2>
          <button class="download-btn" :disabled="!wf.downloadReady" @click="download">下载 Word</button>
        </div>

        <div class="stat-grid">
          <div class="stat-card">
            <span class="stat-value">{{ wf.optimizationSummary?.added_count || 0 }}</span>
            <span class="stat-label">新增</span>
          </div>
          <div class="stat-card">
            <span class="stat-value">{{ wf.optimizationSummary?.modified_count || 0 }}</span>
            <span class="stat-label">修改</span>
          </div>
          <div class="stat-card">
            <span class="stat-value">{{ wf.optimizationSummary?.rewritten_sections?.length || 0 }}</span>
            <span class="stat-label">优化段落</span>
          </div>
          <div class="stat-card">
            <span class="stat-value">{{ wf.optimizationSummary?.added_keywords?.length || 0 }}</span>
            <span class="stat-label">新增关键词</span>
          </div>
        </div>

        <div v-if="wf.optimizationSummary?.added_keywords?.length" class="keyword-block glass-card">
          <span class="block-label">新增岗位关键词</span>
          <div class="tag-list">
            <span v-for="kw in wf.optimizationSummary.added_keywords" :key="kw" class="pill-tag pill-tag--blue">{{ kw }}</span>
          </div>
        </div>

        <div v-if="wf.diffReport?.sections?.length" class="diff-list">
          <div
            v-for="(section, idx) in wf.diffReport.sections"
            :key="`${section.section_type}-${section.section_index}`"
            class="diff-card glass-card"
            v-reveal="{ delay: idx * 80 }"
          >
            <div class="diff-card-header">
              <span class="diff-card-title">{{ section.section_type }} #{{ section.section_index + 1 }}</span>
              <span class="pill-tag" :class="section.changed ? 'pill-tag--warning' : 'pill-tag--muted'">
                {{ section.changed ? '已修改' : '保持不变' }}
              </span>
            </div>
            <div class="diff-panels">
              <div class="diff-panel diff-panel--original">
                <span class="panel-label">原文</span>
                <div class="panel-text">{{ section.original_content }}</div>
              </div>
              <div class="diff-panel diff-panel--optimized">
                <span class="panel-label">优化后</span>
                <div class="panel-text">{{ section.optimized_content }}</div>
              </div>
            </div>
            <div v-if="section.change_reason" class="change-reason">
              <strong>修改说明</strong>
              <p>{{ section.change_reason }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Reset -->
      <div v-if="stage === 'done' || stage === 'error'" class="reset-bar">
        <button class="reset-btn" @click="reset">重新开始</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  max-width: 1200px;
  margin: 0 auto;
  padding-bottom: 80px;
}

/* ===== Hero ===== */
.hero {
  position: relative;
  text-align: center;
  padding: 100px 22px 60px;
  overflow: hidden;
}

.hero-bg {
  position: absolute;
  top: -40%;
  left: 50%;
  transform: translateX(-50%);
  width: 800px;
  height: 800px;
  background: radial-gradient(circle, rgba(0, 113, 227, 0.06) 0%, transparent 70%);
  z-index: -1;
}

.hero-content {
  position: relative;
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
  font-size: 56px;
  font-weight: 700;
  line-height: 1.08;
  letter-spacing: -0.03em;
  margin-bottom: 16px;
}

.hero-subtitle {
  font-size: 21px;
  color: var(--apple-gray-3);
  line-height: 1.5;
  max-width: 520px;
  margin: 0 auto;
}

.hero-meta {
  margin-top: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--apple-gray-4);
  transition: background 0.3s;
}

.status-dot.ok {
  background: #34c759;
  box-shadow: 0 0 0 4px rgba(52, 199, 89, 0.15);
}

.health-text {
  font-size: 13px;
  color: var(--apple-gray-4);
}

/* ===== Pipeline ===== */
.pipeline {
  padding: 0 22px;
}

.error-banner {
  background: rgba(255, 59, 48, 0.06);
  border: 1px solid rgba(255, 59, 48, 0.15);
  border-radius: var(--apple-radius);
  padding: 16px 20px;
  margin-bottom: 24px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.error-banner strong {
  color: #ff3b30;
  font-size: 14px;
}

.error-banner span {
  color: var(--apple-gray-3);
  font-size: 13px;
}

/* ===== Step section ===== */
.step-section {
  margin-bottom: 40px;
  position: relative;
}

.step-card {
  padding: 28px 32px;
  border-radius: var(--apple-radius-lg);
}

.step-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
  transition: transform 0.3s var(--ease-spring);
}

.step-badge--1 { background: rgba(0, 113, 227, 0.1); color: var(--apple-blue); }
.step-badge--2 { background: rgba(175, 82, 222, 0.1); color: #af52de; }
.step-badge--3 { background: rgba(52, 199, 89, 0.1); color: #34c759; }
.step-badge--done { background: rgba(52, 199, 89, 0.12); color: #34c759; font-size: 18px; }

.step-section:hover .step-badge {
  transform: scale(1.08) rotate(-3deg);
}

.step-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--apple-gray-1);
  margin-bottom: 20px;
  letter-spacing: -0.02em;
}

/* ===== Upload ===== */
.apple-upload :deep(.el-upload-dragger) {
  padding: 48px 20px;
  border-radius: var(--apple-radius-lg) !important;
}

.upload-icon-wrap {
  margin-bottom: 8px;
}

.upload-icon-wrap .el-icon {
  font-size: 48px;
  color: var(--apple-blue);
}

.upload-text {
  font-size: 16px;
  color: var(--apple-gray-2);
}

.upload-text em {
  color: var(--apple-blue);
  font-style: normal;
  font-weight: 500;
}

.upload-hint {
  font-size: 13px;
  color: var(--apple-gray-4);
  margin-top: 8px;
}

/* ===== Loading pill ===== */
.loading-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  margin-top: 16px;
  background: var(--apple-gray-6);
  border-radius: 980px;
  font-size: 13px;
  color: var(--apple-gray-3);
}

/* ===== Resume summary ===== */
.resume-summary {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.summary-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.summary-label {
  flex-shrink: 0;
  width: 60px;
  font-size: 13px;
  color: var(--apple-gray-4);
  font-weight: 500;
}

.summary-value {
  font-size: 15px;
  color: var(--apple-gray-1);
}

.summary-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pill-tag {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 980px;
  font-size: 13px;
  background: var(--apple-gray-6);
  color: var(--apple-gray-2);
  transition: transform 0.2s var(--ease-spring);
}

.pill-tag:hover { transform: scale(1.05); }
.pill-tag--success { background: rgba(52, 199, 89, 0.1); color: #248a3d; }
.pill-tag--danger { background: rgba(255, 59, 48, 0.08); color: #c40832; }
.pill-tag--warning { background: rgba(255, 149, 0, 0.1); color: #c77c00; }
.pill-tag--blue { background: rgba(0, 113, 227, 0.08); color: var(--apple-blue); }
.pill-tag--muted { background: var(--apple-gray-6); color: var(--apple-gray-4); }

/* ===== JD divider ===== */
.jd-divider {
  display: flex;
  align-items: center;
  margin: 20px 0;
  max-width: 700px;
}

.jd-divider::before,
.jd-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--apple-gray-5);
}

.jd-divider-text {
  padding: 0 16px;
  font-size: 13px;
  color: var(--apple-gray-4);
}

/* ===== Auto search button ===== */
.auto-search-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 28px;
  background: transparent;
  color: var(--apple-blue);
  border: 1.5px solid var(--apple-blue);
  border-radius: 980px;
  font-size: 15px;
  cursor: pointer;
  transition: all 0.3s var(--ease-spring);
}

.auto-search-btn:hover:not(:disabled) {
  background: var(--apple-blue);
  color: #fff;
  transform: scale(1.02);
  box-shadow: 0 4px 16px rgba(0, 113, 227, 0.15);
}

.auto-search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.auto-search-icon {
  font-size: 16px;
}

/* ===== Job cards grid ===== */
.job-cards-grid {
  margin-top: 24px;
}

.job-cards-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.job-cards-count {
  font-size: 15px;
  font-weight: 600;
  color: var(--apple-gray-1);
}

.job-cards-keywords {
  font-size: 13px;
  color: var(--apple-gray-4);
}

.job-cards-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}

.job-cards-list :deep(.el-card) {
  border-radius: var(--apple-radius) !important;
  border: 1px solid var(--apple-border) !important;
  box-shadow: var(--apple-shadow-sm) !important;
  transition:
    transform 0.3s var(--ease-spring),
    box-shadow 0.3s var(--ease-smooth) !important;
}

.job-cards-list :deep(.el-card:hover) {
  transform: translateY(-4px);
  box-shadow: var(--apple-shadow-md) !important;
}

.job-cards-list :deep(.job-card--selected) {
  border-color: var(--apple-blue) !important;
  box-shadow: 0 0 0 2px rgba(0, 113, 227, 0.2) !important;
}

/* ===== JD input ===== */
.jd-input-wrap {
  display: flex;
  gap: 12px;
  max-width: 700px;
}

.jd-input {
  flex: 1;
  padding: 12px 18px;
  border: 1px solid var(--apple-gray-5);
  border-radius: 980px;
  font-size: 15px;
  color: var(--apple-gray-1);
  background: #fff;
  outline: none;
  transition: all 0.3s var(--ease-smooth);
}

.jd-input:focus {
  border-color: var(--apple-blue);
  box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.1);
}

.jd-input:disabled {
  opacity: 0.5;
}

.jd-submit-btn {
  padding: 12px 24px;
  background: var(--apple-blue);
  color: #fff;
  border: none;
  border-radius: 980px;
  font-size: 15px;
  cursor: pointer;
  transition: all 0.3s var(--ease-spring);
  white-space: nowrap;
}

.jd-submit-btn:hover:not(:disabled) {
  background: var(--apple-blue-hover);
  transform: scale(1.03);
}

.jd-submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== Match result ===== */
.match-grid {
  display: grid;
  grid-template-columns: auto 1fr 1fr;
  gap: 32px;
  align-items: center;
}

.match-score-block {
  text-align: center;
}

.match-score-ring {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: conic-gradient(var(--apple-blue) 0deg, var(--apple-gray-6) 0deg);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
}

.match-score-ring::before {
  content: '';
  position: absolute;
  inset: 6px;
  border-radius: 50%;
  background: #fff;
}

.score-value, .score-suffix {
  position: relative;
  z-index: 1;
}

.score-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--apple-gray-1);
}

.score-suffix {
  font-size: 14px;
  color: var(--apple-gray-4);
}

.score-label {
  display: block;
  margin-top: 8px;
  font-size: 13px;
  color: var(--apple-gray-4);
}

.match-tags-block .block-label {
  display: block;
  font-size: 13px;
  color: var(--apple-gray-3);
  margin-bottom: 10px;
  font-weight: 500;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* ===== Optimize button ===== */
.optimize-btn {
  padding: 14px 36px;
  background: var(--apple-blue);
  color: #fff;
  border: none;
  border-radius: 980px;
  font-size: 17px;
  cursor: pointer;
  transition: all 0.3s var(--ease-spring);
}

.optimize-btn:hover:not(:disabled) {
  background: var(--apple-blue-hover);
  transform: scale(1.03);
  box-shadow: 0 8px 24px rgba(0, 113, 227, 0.3);
}

.optimize-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-loading {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

/* ===== Result header ===== */
.result-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.download-btn {
  margin-left: auto;
  padding: 8px 20px;
  background: #34c759;
  color: #fff;
  border: none;
  border-radius: 980px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s var(--ease-spring);
}

.download-btn:hover:not(:disabled) {
  transform: scale(1.04);
  box-shadow: 0 4px 16px rgba(52, 199, 89, 0.3);
}

.download-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== Stat grid ===== */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  padding: 24px;
  background: #fff;
  border-radius: var(--apple-radius);
  border: 1px solid var(--apple-border);
  text-align: center;
  transition: transform 0.3s var(--ease-spring);
}

.stat-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--apple-shadow-md);
}

.stat-value {
  display: block;
  font-size: 36px;
  font-weight: 700;
  color: var(--apple-gray-1);
}

.stat-label {
  display: block;
  margin-top: 4px;
  font-size: 13px;
  color: var(--apple-gray-4);
}

/* ===== Keyword block ===== */
.keyword-block {
  padding: 16px 20px;
  margin-bottom: 24px;
}

/* ===== Diff list ===== */
.diff-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.diff-card {
  padding: 24px 28px;
  border-radius: var(--apple-radius);
}

.diff-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.diff-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--apple-gray-1);
}

.diff-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.diff-panel {
  border-radius: 14px;
  overflow: hidden;
}

.diff-panel--original { background: var(--apple-gray-6); }
.diff-panel--optimized { background: rgba(52, 199, 89, 0.04); }

.panel-label {
  display: block;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--apple-gray-4);
  border-bottom: 1px solid var(--apple-border);
}

.panel-text {
  padding: 14px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--apple-gray-2);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.change-reason {
  margin-top: 16px;
  padding: 14px 16px;
  background: var(--apple-gray-6);
  border-radius: 12px;
}

.change-reason strong {
  display: block;
  font-size: 13px;
  color: var(--apple-gray-3);
  margin-bottom: 4px;
}

.change-reason p {
  font-size: 14px;
  color: var(--apple-gray-2);
  line-height: 1.6;
}

/* ===== Reset ===== */
.reset-bar {
  text-align: center;
  padding: 20px 0;
}

.reset-btn {
  padding: 10px 28px;
  background: transparent;
  border: 1px solid var(--apple-gray-5);
  border-radius: 980px;
  font-size: 14px;
  color: var(--apple-blue);
  cursor: pointer;
  transition: all 0.3s var(--ease-spring);
}

.reset-btn:hover {
  background: var(--apple-blue);
  color: #fff;
  border-color: var(--apple-blue);
  transform: scale(1.03);
}

/* ===== 浮动背景光球 ===== */
.bg-orbs {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: -1;
  pointer-events: none;
  overflow: hidden;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  transition: transform 0.6s var(--ease-smooth);
}

.orb--1 {
  top: 8%;
  right: 5%;
  width: 380px;
  height: 380px;
  background: radial-gradient(circle, rgba(0, 113, 227, 0.12) 0%, transparent 70%);
  animation: float 8s ease-in-out infinite;
}

.orb--2 {
  top: 45%;
  left: 3%;
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, rgba(175, 82, 222, 0.10) 0%, transparent 70%);
  animation: float 6s ease-in-out infinite reverse;
}

.orb--3 {
  bottom: 10%;
  right: 15%;
  width: 260px;
  height: 260px;
  background: radial-gradient(circle, rgba(52, 199, 89, 0.10) 0%, transparent 70%);
  animation: float 7s ease-in-out infinite;
}

/* ===== 功能亮点 ===== */
.features {
  padding: 0 22px;
  margin-bottom: 60px;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.feature-card {
  position: relative;
  padding: 32px 28px;
  overflow: hidden;
  cursor: default;
}

.feature-icon {
  width: 56px;
  height: 56px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  margin-bottom: 16px;
  transition: transform 0.4s var(--ease-spring);
}

.feature-card:hover .feature-icon {
  transform: scale(1.1) rotate(-5deg);
}

.feature-title {
  font-size: 19px;
  font-weight: 600;
  color: var(--apple-gray-1);
  margin-bottom: 8px;
}

.feature-desc {
  font-size: 14px;
  color: var(--apple-gray-3);
  line-height: 1.6;
}

.feature-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 3px;
  transform-origin: left;
  transition: transform 0.4s var(--ease-spring);
}

/* ===== 使用流程 ===== */
.how-it-works {
  padding: 0 22px;
  margin-bottom: 60px;
  text-align: center;
}

.section-heading {
  font-size: 32px;
  font-weight: 700;
  color: var(--apple-gray-1);
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}

.section-sub {
  font-size: 16px;
  color: var(--apple-gray-4);
  margin-bottom: 40px;
}

.steps-track {
  position: relative;
  display: flex;
  justify-content: space-between;
  max-width: 800px;
  margin: 0 auto;
  gap: 20px;
}

.steps-line {
  position: absolute;
  top: 24px;
  left: 10%;
  right: 10%;
  height: 2px;
  background: var(--apple-gray-5);
  z-index: 0;
}

.step-node {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  flex: 1;
}

.step-circle {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid var(--apple-gray-5);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
  color: var(--apple-gray-4);
  transition: all 0.4s var(--ease-spring);
}

.step-node.active .step-circle {
  border-color: var(--apple-blue);
  color: var(--apple-blue);
  background: rgba(0, 113, 227, 0.06);
  transform: scale(1.15);
  box-shadow: 0 0 0 6px rgba(0, 113, 227, 0.08);
}

.step-node.done .step-circle {
  border-color: #34c759;
  color: #34c759;
  background: rgba(52, 199, 89, 0.06);
}

.step-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.step-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--apple-gray-2);
}

.step-desc {
  font-size: 12px;
  color: var(--apple-gray-4);
  max-width: 160px;
  text-align: center;
  line-height: 1.5;
}

/* ===== 统计带 ===== */
.stats-band {
  display: flex;
  justify-content: space-around;
  margin: 0 22px 60px;
  padding: 36px 0;
  background: var(--apple-gray-6);
  border-radius: var(--apple-radius-lg);
}

.stats-item {
  text-align: center;
}

.stats-num {
  display: block;
  font-size: 40px;
  font-weight: 700;
  color: var(--apple-gray-1);
  letter-spacing: -0.02em;
}

.stats-suffix {
  font-size: 20px;
  font-weight: 600;
  color: var(--apple-gray-3);
}

.stats-label {
  display: block;
  margin-top: 4px;
  font-size: 13px;
  color: var(--apple-gray-4);
}

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .hero-title { font-size: 36px; }
  .hero-subtitle { font-size: 17px; }
  .match-grid { grid-template-columns: 1fr; }
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .diff-panels { grid-template-columns: 1fr; }
  .jd-input-wrap { flex-direction: column; }
  .job-cards-list { grid-template-columns: 1fr; }
  .features-grid { grid-template-columns: 1fr; }
  .steps-track { flex-direction: column; gap: 24px; }
  .steps-line { display: none; }
  .stats-band { flex-wrap: wrap; gap: 20px; }
  .stats-item { width: 45%; }
  .stats-num { font-size: 32px; }
}
</style>
