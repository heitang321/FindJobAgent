<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import { ChatDotRound, Loading, Promotion, Delete, Folder } from '@element-plus/icons-vue'
import { getChatSessions, getChatMessages, deleteChatSession, checkHealth } from '@/api'

const healthStatus = ref('检测中...')
const messages = ref([])
const inputText = ref('')
const isThinking = ref(false)
const chatBodyRef = ref(null)
const currentSessionId = ref(null)

// ===== 会话历史侧边栏 =====
const sessions = ref([])
const showHistory = ref(false)

// ===== 鼠标视差 =====
const parallaxX = ref(0)
const parallaxY = ref(0)

function handleMouseMove(e) {
  const cx = window.innerWidth / 2
  const cy = window.innerHeight / 2
  parallaxX.value = (e.clientX - cx) / cx
  parallaxY.value = (e.clientY - cy) / cy
}

// ===== 快捷问题 =====
const quickQuestions = [
  { text: '帮我画一个柱状图展示编程语言流行度', icon: '📊', type: 'chart' },
  { text: '搜索 Python 后端岗位', icon: '💼', type: 'job_search' },
  { text: '如何优化我的简历？', icon: '📝', type: 'resume_advice' },
  { text: '面试时如何介绍项目经验？', icon: '🎯', type: 'interview' },
  { text: '数据分析：如何评估简历匹配度', icon: '🔍', type: 'analysis' },
  { text: '上海 Java 开发薪资多少？', icon: '💰', type: 'salary' },
]

// ===== 功能卡片 =====
const features = [
  { icon: '📊', title: '图表生成', desc: '描述你想要的图表，AI 自动生成 ECharts 可视化', color: '#0071e3' },
  { icon: '💼', title: '岗位搜索', desc: '直接对话搜索招聘岗位，实时返回岗位卡片', color: '#34c759' },
  { icon: '📝', title: '简历优化', desc: '提出简历问题，获取修改建议和优化引导', color: '#af52de' },
  { icon: '🎯', title: '面试准备', desc: '自我介绍、面试题、STAR 法则，一站搞定', color: '#ff9500' },
]

// ===== ECharts 实例管理 =====
const chartInstances = ref([])

function renderChart(messageId, optionStr) {
  console.log('[renderChart] called, messageId:', messageId)
  // 用 setTimeout 替代 nextTick，确保 DOM 已完全渲染
  let retries = 0
  const tryRender = () => {
    const el = document.getElementById(`chart-${messageId}`)
    console.log('[renderChart] try', retries, 'el:', !!el, 'size:', el ? `${el.offsetWidth}x${el.offsetHeight}` : 'N/A')
    if (!el) {
      if (retries++ < 10) {
        setTimeout(tryRender, 100)
      } else {
        console.error('[renderChart] chart container not found after 10 retries:', messageId)
      }
      return
    }
    // 销毁旧实例
    const existing = chartInstances.value.find((c) => c.id === messageId)
    if (existing) {
      existing.instance.dispose()
      chartInstances.value = chartInstances.value.filter((c) => c.id !== messageId)
    }
    // 解析 option
    let option
    try {
      option = JSON.parse(optionStr)
    } catch (e) {
      el.innerHTML = '<span style="color:#ff3b30;font-size:13px">图表数据解析失败</span>'
      console.error('[renderChart] JSON parse error:', e)
      return
    }
    // 动态导入 echarts，避免打包问题
    import('echarts').then((echarts) => {
      try {
        const chart = echarts.init(el)
        chart.setOption(option)
        chartInstances.value.push({ id: messageId, instance: chart })
        window.addEventListener('resize', chart.resize)
      } catch (e) {
        el.innerHTML = '<span style="color:#ff3b30;font-size:13px">图表初始化失败</span>'
        console.error('[renderChart] echarts.init error:', e)
      }
    }).catch((e) => {
      el.innerHTML = '<span style="color:#ff3b30;font-size:13px">echarts 模块加载失败</span>'
      console.error('[renderChart] echarts import error:', e)
    })
  }
  setTimeout(tryRender, 50)
}

function scrollToBottom() {
  nextTick(() => {
    if (chatBodyRef.value) {
      chatBodyRef.value.scrollTop = chatBodyRef.value.scrollHeight
    }
  })
}

// ===== 发送消息（SSE 流式） =====
async function sendMessage(text) {
  const question = (text ?? inputText.value).trim()
  if (!question || isThinking.value) return

  // 添加用户消息
  const userMsgId = Date.now()
  messages.value.push({ id: userMsgId, role: 'user', content: question })
  inputText.value = ''
  isThinking.value = true
  scrollToBottom()

  // 添加 AI 消息占位（流式逐字更新）
  const aiMsgId = Date.now() + 1
  messages.value.push({
    id: aiMsgId,
    role: 'assistant',
    type: 'qa',
    content: '',
  })
  const aiMsgIndex = messages.value.length - 1
  scrollToBottom()

  try {
    const token = localStorage.getItem('token') || ''
    const response = await fetch('/api/v1/chat/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        question,
        session_id: currentSessionId.value,
      }),
    })

    if (!response.ok) {
      let detail = '请求失败'
      try {
        const err = await response.json()
        detail = err.detail || detail
      } catch { /* ignore */ }
      throw new Error(detail)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() // 保留不完整的行

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        let data
        try {
          data = JSON.parse(line.slice(6))
        } catch {
          continue
        }

        if (data.type === 'start') {
          // 不在 start 事件设置 type，保持 'qa' 让 delta 文本可见
          // 只有 chart/job_search 数据事件到达时才切换类型
          if (data.session_id) currentSessionId.value = data.session_id
        } else if (data.type === 'delta') {
          messages.value[aiMsgIndex].content += data.content
          scrollToBottom()
        } else if (data.type === 'chart') {
          console.log('[SSE] chart event received, aiMsgId:', aiMsgId, 'dataLen:', data.data?.length)
          // 清空之前的 delta 文本，设置图表数据
          messages.value[aiMsgIndex].content = data.data
          messages.value[aiMsgIndex].type = 'chart'
          scrollToBottom()
          // 渲染图表（renderChart 内部用 setTimeout 确保 DOM 就绪）
          renderChart(aiMsgId, data.data)
        } else if (data.type === 'job_search') {
          messages.value[aiMsgIndex].content = data.data
          messages.value[aiMsgIndex].type = 'job_search'
          if (data.keywords) messages.value[aiMsgIndex].keywords = data.keywords
          scrollToBottom()
        } else if (data.type === 'error') {
          // 如果是图表生成失败，type 还是 qa，文本可以正常显示
          messages.value[aiMsgIndex].content += `\n\n⚠️ ${data.content}`
          scrollToBottom()
        } else if (data.type === 'end') {
          // 完成
        }
      }
    }

    // 刷新会话列表
    loadSessions()
  } catch (e) {
    messages.value[aiMsgIndex].content = e.message || '回答失败，请稍后重试'
    messages.value[aiMsgIndex].type = 'error'
    scrollToBottom()
  } finally {
    isThinking.value = false
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// ===== 新建对话 =====
function startNewChat() {
  messages.value = []
  currentSessionId.value = null
  inputText.value = ''
}

// ===== 加载会话列表 =====
async function loadSessions() {
  try {
    const data = await getChatSessions()
    sessions.value = data.sessions || []
  } catch {
    // 静默失败
  }
}

// ===== 加载历史会话消息 =====
async function loadSessionMessages(sessionId) {
  try {
    const data = await getChatMessages(sessionId)
    messages.value = (data.messages || []).map((m, i) => ({
      id: Date.now() + i,
      role: m.role,
      type: m.type,
      content: m.content,
      keywords: m.keywords,
    }))
    currentSessionId.value = sessionId
    showHistory.value = false
    // 如果有图表消息，延迟渲染
    nextTick(() => {
      messages.value.forEach((msg) => {
        if (msg.role === 'assistant' && msg.type === 'chart') {
          renderChart(msg.id, msg.content)
        }
      })
      scrollToBottom()
    })
  } catch {
    ElMessage.error('加载会话失败')
  }
}

// ===== 删除会话 =====
async function handleDeleteSession(sessionId) {
  try {
    await ElMessageBox.confirm('确定删除这个会话吗？', '提示', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return // 用户取消
  }
  try {
    await deleteChatSession(sessionId)
    ElMessage.success('已删除')
    if (currentSessionId.value === sessionId) {
      startNewChat()
    }
    loadSessions()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message || '删除失败')
  }
}

// ===== 解析岗位卡片 =====
function parseJobCards(content) {
  try {
    const cards = JSON.parse(content)
    return Array.isArray(cards) ? cards : []
  } catch {
    return []
  }
}

function openJobUrl(url) {
  if (url) window.open(url, '_blank')
}

async function checkApi() {
  try {
    const data = await checkHealth()
    healthStatus.value = data.status === 'ok' ? 'API 正常' : '异常'
  } catch {
    healthStatus.value = 'API 不可用'
  }
}

onMounted(() => {
  checkApi()
  loadSessions()
})

onUnmounted(() => {
  chartInstances.value.forEach((c) => {
    window.removeEventListener('resize', c.instance.resize)
    c.instance.dispose()
  })
})

// ===== Markdown 渲染 =====
function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function renderMarkdown(text) {
  if (!text) return ''
  let html = text
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) =>
      `<pre class="md-code-block"><code>${escapeHtml(code.trim())}</code></pre>`)
    .replace(/`([^`]+)`/g, '<code class="md-code-inline">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/^### (.+)$/gm, '<h4 class="md-h4">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="md-h3">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 class="md-h2">$1</h2>')
    .replace(/^- (.+)$/gm, '<li class="md-li">$1</li>')
    .replace(/^\|(.+)\|$/gm, (match) => {
      const cells = match.split('|').filter((c) => c.trim())
      const tds = cells.map((c) => `<td class="md-td">${c.trim()}</td>`).join('')
      return `<tr>${tds}</tr>`
    })
  html = html.replace(/(<li class="md-li">[\s\S]*?<\/li>(?:\n?<li class="md-li">[\s\S]*?<\/li>)*)/g,
    (m) => `<ul class="md-ul">${m}</ul>`)
  html = html.replace(/(<tr>[\s\S]*?<\/tr>(?:\n?<tr>[\s\S]*?<\/tr>)*)/g,
    (m) => `<table class="md-table">${m}</table>`)
  return html
}
</script>

<template>
  <div class="home" @mousemove="handleMouseMove">
    <!-- ===== 浮动背景光球 ===== -->
    <div class="bg-orbs">
      <div class="orb orb--1" :style="{ transform: `translate(${parallaxX * 30}px, ${parallaxY * 30}px)` }"></div>
      <div class="orb orb--2" :style="{ transform: `translate(${parallaxX * -20}px, ${parallaxY * -25}px)` }"></div>
      <div class="orb orb--3" :style="{ transform: `translate(${parallaxX * 15}px, ${parallaxY * -15}px)` }"></div>
    </div>

    <!-- ===== 会话历史侧边栏 ===== -->
    <transition name="slide-fade">
      <div v-if="showHistory" class="history-sidebar glass-card">
        <div class="history-header">
          <span class="history-title">历史会话</span>
          <button class="history-close" @click="showHistory = false">✕</button>
        </div>
        <button class="new-chat-btn" @click="startNewChat">
          <span>＋</span> 新建对话
        </button>
        <div class="history-list">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="history-item"
            :class="{ active: currentSessionId === s.id }"
            @click="loadSessionMessages(s.id)"
          >
            <div class="history-item-title">{{ s.title || '未命名对话' }}</div>
            <div class="history-item-time">{{ (s.created_at || '').slice(0, 16).replace('T', ' ') }}</div>
            <button class="history-item-delete" @click.stop="handleDeleteSession(s.id)">
              <el-icon><Delete /></el-icon>
            </button>
          </div>
          <div v-if="sessions.length === 0" class="history-empty">暂无历史会话</div>
        </div>
      </div>
    </transition>

    <!-- ===== Hero + 居中输入 ===== -->
    <section class="hero" v-if="messages.length === 0">
      <button class="history-toggle-btn glass-card" @click="showHistory = !showHistory">
        <el-icon><Folder /></el-icon>
        <span>历史</span>
      </button>
      <div class="hero-content">
        <p class="hero-eyebrow anim-fade-in">FindJobAgent</p>
        <h1 class="hero-title anim-fade-up delay-1">
          智能问答<span class="gradient-text-blue">助手</span>
        </h1>
        <p class="hero-subtitle anim-fade-up delay-2">
          岗位搜索 · 简历优化 · 面试准备 · 图表生成，一个对话框搞定。
        </p>
        <div class="hero-meta anim-fade-up delay-3">
          <span class="status-dot" :class="{ ok: healthStatus === 'API 正常' }"></span>
          <span class="health-text">{{ healthStatus }}</span>
        </div>

        <div class="hero-input anim-fade-up delay-4">
          <div class="chat-input-wrap hero-input-wrap">
            <input
              v-model="inputText"
              type="text"
              class="chat-input"
              placeholder="问我任何问题... (岗位搜索 / 简历优化 / 面试技巧 / 画图表)"
              :disabled="isThinking"
              @keydown="handleKeydown"
            />
            <button
              class="chat-send-btn"
              :disabled="!inputText.trim() || isThinking"
              @click="sendMessage()"
            >
              <span v-if="isThinking" class="btn-loading">
                <el-icon class="is-loading"><Loading /></el-icon>
              </span>
              <el-icon v-else class="send-icon"><Promotion /></el-icon>
            </button>
          </div>
        </div>

        <div class="quick-questions anim-fade-up delay-5">
          <div class="quick-grid">
            <button
              v-for="q in quickQuestions"
              :key="q.text"
              class="quick-chip"
              :disabled="isThinking"
              @click="sendMessage(q.text)"
            >
              <span class="quick-icon">{{ q.icon }}</span>
              <span>{{ q.text }}</span>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 功能亮点 ===== -->
    <section class="features" v-if="messages.length === 0">
      <div class="features-grid">
        <div
          v-for="(f, i) in features"
          :key="f.title"
          class="feature-card glass-card"
          v-reveal="{ delay: i * 120 }"
        >
          <div class="feature-icon" :style="{ background: `${f.color}15`, color: f.color }">
            {{ f.icon }}
          </div>
          <h3 class="feature-title">{{ f.title }}</h3>
          <p class="feature-desc">{{ f.desc }}</p>
          <div class="feature-bar" :style="{ background: f.color }"></div>
        </div>
      </div>
    </section>

    <!-- ===== 聊天区域 ===== -->
    <section class="chat-section" v-if="messages.length > 0">
      <div class="chat-header">
        <button class="chat-history-btn" @click="showHistory = !showHistory">
          <el-icon><Folder /></el-icon>
        </button>
        <el-icon class="chat-header-icon"><ChatDotRound /></el-icon>
        <span>智能对话</span>
        <button class="chat-new-btn" @click="startNewChat">＋ 新建</button>
      </div>
      <div class="chat-body" ref="chatBodyRef">
        <div
          v-for="msg in messages"
          :key="msg.id"
          class="msg-row"
          :class="msg.role === 'user' ? 'msg-row--user' : 'msg-row--ai'"
        >
          <div class="msg-avatar" :class="msg.role === 'user' ? 'msg-avatar--user' : 'msg-avatar--ai'">
            {{ msg.role === 'user' ? '我' : 'AI' }}
          </div>
          <div class="msg-bubble" :class="[
            msg.role === 'user' ? 'msg-bubble--user' : 'msg-bubble--ai',
            msg.role === 'assistant' && (msg.type === 'chart' || msg.type === 'job_search') ? 'msg-bubble--wide' : ''
          ]">
            <!-- 图表回答 -->
            <div v-if="msg.role === 'assistant' && msg.type === 'chart'" class="msg-chart">
              <div :id="`chart-${msg.id}`" class="chart-container"></div>
            </div>
            <!-- 岗位搜索回答 -->
            <div v-else-if="msg.role === 'assistant' && msg.type === 'job_search'" class="msg-jobs">
              <p class="jobs-intro">🔍 为你找到以下岗位：</p>
              <div class="job-cards-grid">
                <div
                  v-for="(card, idx) in parseJobCards(msg.content)"
                  :key="idx"
                  class="job-card-mini"
                  @click="openJobUrl(card.url)"
                >
                  <div class="job-card-header">
                    <span class="job-card-title">{{ card.title }}</span>
                    <span class="job-card-salary" v-if="card.salary">{{ card.salary }}</span>
                  </div>
                  <div class="job-card-company" v-if="card.company">{{ card.company }}</div>
                  <div class="job-card-meta">
                    <span v-if="card.location">📍 {{ card.location }}</span>
                    <span v-if="card.experience">⏱ {{ card.experience }}</span>
                    <span v-if="card.education">🎓 {{ card.education }}</span>
                  </div>
                  <div class="job-card-skills" v-if="card.skills && card.skills.length">
                    <span v-for="skill in card.skills.slice(0, 5)" :key="skill" class="job-skill-tag">{{ skill }}</span>
                  </div>
                </div>
              </div>
            </div>
            <!-- 文字回答（流式逐字渲染） -->
            <div v-else class="msg-text" v-html="renderMarkdown(msg.content)"></div>
          </div>
        </div>
        <!-- 思考中 -->
        <div v-if="isThinking && messages.length > 0 && !messages[messages.length - 1]?.content" class="msg-row msg-row--ai">
          <div class="msg-avatar msg-avatar--ai">AI</div>
          <div class="msg-bubble msg-bubble--ai">
            <div class="thinking-dots">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入框 -->
      <div class="chat-input-area">
        <div class="chat-input-wrap">
          <input
            v-model="inputText"
            type="text"
            class="chat-input"
            placeholder="输入你的问题... (岗位搜索 / 简历优化 / 面试 / 图表)"
            :disabled="isThinking"
            @keydown="handleKeydown"
          />
          <button
            class="chat-send-btn"
            :disabled="!inputText.trim() || isThinking"
            @click="sendMessage()"
          >
            <span v-if="isThinking" class="btn-loading">
              <el-icon class="is-loading"><Loading /></el-icon>
            </span>
            <el-icon v-else class="send-icon"><Promotion /></el-icon>
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  max-width: 1200px;
  margin: 0 auto;
  padding-bottom: 120px;
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

/* ===== Hero ===== */
.hero {
  position: relative;
  text-align: center;
  padding: 80px 22px 40px;
  overflow: hidden;
}

.history-toggle-btn {
  position: absolute;
  top: 20px;
  left: 22px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 980px;
  font-size: 14px;
  color: var(--apple-gray-2);
  cursor: pointer;
  transition: all 0.3s var(--ease-spring);
}

.history-toggle-btn:hover {
  color: var(--apple-blue);
  border-color: var(--apple-blue);
}

.hero-content { position: relative; }

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
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--apple-gray-4);
  transition: background 0.3s;
}

.status-dot.ok {
  background: #34c759;
  box-shadow: 0 0 0 4px rgba(52, 199, 89, 0.15);
}

.health-text { font-size: 13px; color: var(--apple-gray-4); }

/* ===== 功能亮点 ===== */
.features { padding: 0 22px; margin-bottom: 50px; }
.features-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
.feature-card { position: relative; padding: 28px 22px; overflow: hidden; cursor: default; }
.feature-icon {
  width: 48px; height: 48px;
  border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; margin-bottom: 14px;
  transition: transform 0.4s var(--ease-spring);
}
.feature-card:hover .feature-icon { transform: scale(1.1) rotate(-5deg); }
.feature-title { font-size: 17px; font-weight: 600; color: var(--apple-gray-1); margin-bottom: 6px; }
.feature-desc { font-size: 13px; color: var(--apple-gray-3); line-height: 1.5; }
.feature-bar {
  position: absolute; bottom: 0; left: 0;
  width: 100%; height: 3px;
  transform-origin: left; transform: scaleX(0);
  transition: transform 0.4s var(--ease-spring);
}
.feature-card:hover .feature-bar { transform: scaleX(1); }

/* ===== 快捷问题 ===== */
.quick-questions { margin-top: 40px; }
.quick-grid { display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; }
.quick-chip {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 10px 18px;
  background: #fff;
  border: 1px solid var(--apple-gray-5);
  border-radius: 980px;
  font-size: 14px; color: var(--apple-gray-2);
  cursor: pointer;
  transition: all 0.3s var(--ease-spring);
}
.quick-chip:hover {
  border-color: var(--apple-blue);
  color: var(--apple-blue);
  background: rgba(0, 113, 227, 0.04);
  transform: scale(1.03);
}
.quick-icon { font-size: 18px; }

/* ===== Hero 居中输入 ===== */
.hero-input { margin-top: 32px; max-width: 680px; margin-left: auto; margin-right: auto; }
.hero-input-wrap { box-shadow: var(--apple-shadow-md); }

/* ===== 会话历史侧边栏 ===== */
.history-sidebar {
  position: fixed;
  top: 80px; left: 20px;
  width: 280px;
  max-height: calc(100vh - 120px);
  z-index: 100;
  display: flex; flex-direction: column;
  padding: 0; overflow: hidden;
}
.history-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--apple-border);
}
.history-title { font-size: 16px; font-weight: 600; color: var(--apple-gray-1); }
.history-close {
  background: none; border: none;
  font-size: 18px; color: var(--apple-gray-4);
  cursor: pointer; padding: 4px 8px; border-radius: 8px;
  transition: all 0.2s;
}
.history-close:hover { background: var(--apple-gray-6); }
.new-chat-btn {
  margin: 12px 16px;
  padding: 10px 16px;
  border-radius: 12px;
  border: 1px solid var(--apple-blue);
  background: rgba(0, 113, 227, 0.06);
  color: var(--apple-blue);
  font-size: 14px; font-weight: 500;
  cursor: pointer;
  display: flex; align-items: center; gap: 6px;
  transition: all 0.2s;
}
.new-chat-btn:hover { background: var(--apple-blue); color: #fff; }
.history-list { flex: 1; overflow-y: auto; padding: 0 8px 12px; }
.history-item {
  position: relative;
  padding: 12px 14px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 4px;
}
.history-item:hover { background: var(--apple-gray-6); }
.history-item.active { background: rgba(0, 113, 227, 0.08); }
.history-item-title {
  font-size: 14px; color: var(--apple-gray-2);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  margin-bottom: 4px;
}
.history-item-time { font-size: 12px; color: var(--apple-gray-4); }
.history-item-delete {
  position: absolute; top: 50%; right: 8px;
  transform: translateY(-50%);
  background: none; border: none;
  color: var(--apple-gray-4);
  cursor: pointer; padding: 4px;
  border-radius: 6px; opacity: 0;
  transition: all 0.2s;
}
.history-item:hover .history-item-delete { opacity: 1; }
.history-item-delete:hover { background: rgba(255, 59, 48, 0.1); color: #ff3b30; }
.history-empty { text-align: center; padding: 30px 0; color: var(--apple-gray-4); font-size: 14px; }

/* ===== 聊天区域 ===== */
.chat-section {
  display: flex; flex-direction: column;
  height: calc(100vh - var(--header-height) - 40px);
  padding: 0 22px;
}
.chat-header {
  display: flex; align-items: center; gap: 8px;
  padding: 16px 0 12px;
  font-size: 18px; font-weight: 600; color: var(--apple-gray-1);
}
.chat-history-btn {
  background: none; border: 1px solid var(--apple-border);
  border-radius: 10px; padding: 6px 10px;
  cursor: pointer; color: var(--apple-gray-3); font-size: 18px;
  transition: all 0.2s;
}
.chat-history-btn:hover { color: var(--apple-blue); border-color: var(--apple-blue); }
.chat-header-icon { font-size: 22px; color: var(--apple-blue); }
.chat-new-btn {
  margin-left: auto; padding: 6px 14px;
  border-radius: 980px; border: 1px solid var(--apple-blue);
  background: transparent; color: var(--apple-blue);
  font-size: 13px; cursor: pointer; transition: all 0.2s;
}
.chat-new-btn:hover { background: var(--apple-blue); color: #fff; }

.chat-body {
  flex: 1; overflow-y: auto;
  padding: 8px 0 16px;
  display: flex; flex-direction: column; gap: 16px;
}

/* ===== 消息行 ===== */
.msg-row { display: flex; gap: 12px; align-items: flex-start; animation: fadeUp 0.4s var(--ease-spring) both; }
.msg-row--user { flex-direction: row-reverse; }
.msg-avatar {
  flex-shrink: 0; width: 36px; height: 36px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
}
.msg-avatar--user { background: var(--apple-blue); color: #fff; }
.msg-avatar--ai { background: var(--apple-gray-6); color: var(--apple-gray-2); border: 1px solid var(--apple-border); }
.msg-bubble {
  max-width: 75%; padding: 14px 18px;
  border-radius: 18px;
  font-size: 15px; line-height: 1.7; word-break: break-word; overflow: hidden;
}
.msg-bubble--user { background: var(--apple-blue); color: #fff; border-bottom-right-radius: 4px; }
.msg-bubble--ai { background: #fff; color: var(--apple-gray-1); border: 1px solid var(--apple-border); border-bottom-left-radius: 4px; }
/* 岗位卡片和图表需要更宽的空间 + 确保 flex 布局下宽度不为 0 */
.msg-bubble--ai.msg-bubble--wide { max-width: 90%; flex: 1 1 80%; min-width: 400px; }

/* ===== 图表容器 ===== */
.msg-chart { width: 100%; }
.chart-container { width: 100%; min-width: 350px; height: 360px; border-radius: 12px; overflow: hidden; background: #fff; }

/* ===== 岗位卡片 ===== */
.msg-jobs { width: 100%; }
.jobs-intro { font-size: 14px; color: var(--apple-gray-2); margin-bottom: 12px; font-weight: 500; }
.job-cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; width: 100%; }
.job-card-mini {
  padding: 14px; border: 1px solid var(--apple-border);
  border-radius: 14px; cursor: pointer;
  transition: all 0.3s var(--ease-spring); background: #fff;
}
.job-card-mini:hover { border-color: var(--apple-blue); box-shadow: 0 4px 16px rgba(0, 113, 227, 0.1); transform: translateY(-2px); }
.job-card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.job-card-title { font-size: 14px; font-weight: 600; color: var(--apple-gray-1); flex: 1; line-height: 1.4; }
.job-card-salary { font-size: 13px; color: #ff6b35; font-weight: 600; white-space: nowrap; }
.job-card-company { font-size: 12px; color: var(--apple-gray-3); margin-bottom: 6px; }
.job-card-meta { display: flex; flex-wrap: wrap; gap: 8px; font-size: 11px; color: var(--apple-gray-4); margin-bottom: 8px; }
.job-card-skills { display: flex; flex-wrap: wrap; gap: 4px; }
.job-skill-tag { padding: 2px 8px; border-radius: 6px; background: var(--apple-gray-6); font-size: 11px; color: var(--apple-gray-2); }

/* ===== Markdown 样式 ===== */
:deep(.md-h2) { font-size: 18px; font-weight: 700; margin: 8px 0; }
:deep(.md-h3) { font-size: 16px; font-weight: 600; margin: 6px 0; }
:deep(.md-h4) { font-size: 14px; font-weight: 600; margin: 4px 0; }
:deep(.md-ul) { margin: 4px 0; padding-left: 20px; }
:deep(.md-li) { margin: 2px 0; }
:deep(.md-code-inline) { background: var(--apple-gray-6); padding: 2px 6px; border-radius: 4px; font-size: 13px; font-family: 'SF Mono', 'Fira Code', monospace; }
:deep(.md-code-block) { background: #1d1d1f; color: #f5f5f7; padding: 14px 16px; border-radius: 12px; overflow-x: auto; margin: 8px 0; font-size: 13px; line-height: 1.5; }
:deep(.md-table) { border-collapse: collapse; margin: 8px 0; width: 100%; }
:deep(.md-td) { border: 1px solid var(--apple-gray-5); padding: 6px 12px; font-size: 14px; }

/* ===== 思考动画 ===== */
.thinking-dots { display: flex; gap: 6px; padding: 4px 0; }
.thinking-dots span { width: 8px; height: 8px; border-radius: 50%; background: var(--apple-gray-4); animation: pulse-soft 1.2s ease-in-out infinite; }
.thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.4s; }

/* ===== 输入栏 ===== */
.chat-input-area { padding: 12px 0 16px; }
.chat-input-wrap {
  display: flex; gap: 10px;
  background: #fff; border: 1px solid var(--apple-gray-5);
  border-radius: 980px; padding: 6px 6px 6px 18px;
  transition: border-color 0.3s var(--ease-smooth), box-shadow 0.3s var(--ease-smooth);
}
.chat-input-wrap:focus-within { border-color: var(--apple-blue); box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.1); }
.chat-input { flex: 1; border: none; outline: none; font-size: 15px; color: var(--apple-gray-1); background: transparent; }
.chat-input::placeholder { color: var(--apple-gray-4); }
.chat-send-btn {
  flex-shrink: 0; width: 40px; height: 40px;
  border-radius: 50%; border: none;
  background: var(--apple-blue); color: #fff;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.3s var(--ease-spring);
}
.chat-send-btn:hover:not(:disabled) { background: var(--apple-blue-hover); transform: scale(1.08); }
.chat-send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.send-icon { font-size: 18px; }
.btn-loading { display: flex; align-items: center; justify-content: center; }

/* ===== 侧边栏动画 ===== */
.slide-fade-enter-active { transition: all 0.3s var(--ease-spring); }
.slide-fade-leave-active { transition: all 0.2s var(--ease-smooth); }
.slide-fade-enter-from, .slide-fade-leave-to { transform: translateX(-20px); opacity: 0; }

/* ===== Responsive ===== */
@media (max-width: 768px) {
  .hero-title { font-size: 36px; }
  .hero-subtitle { font-size: 17px; }
  .features-grid { grid-template-columns: repeat(2, 1fr); }
  .msg-bubble { max-width: 85%; }
  .chart-container { height: 280px; }
  .history-sidebar { width: calc(100vw - 40px); }
}
</style>
