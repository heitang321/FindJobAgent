<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, CircleCheck, Lock, Message, User } from '@element-plus/icons-vue'
import { sendAuthCode } from '@/api'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const mode = ref('login')
const loading = ref(false)
const sendingCode = ref(false)
const countdown = ref(0)
const formError = ref('')
let countdownTimer = null

const form = reactive({
  email: '',
  username: '',
  password: '',
  confirmPassword: '',
  verification_code: '',
})

const isRegister = computed(() => mode.value === 'register')
const title = computed(() => (isRegister.value ? '创建你的账号。' : '欢迎回来。'))
const subtitle = computed(() =>
  isRegister.value
    ? '用邮箱验证码完成注册，开始你的简历优化工作流。'
    : '邮箱、密码和验证码一起校验，让本地测试也保持真实流程。',
)
const canSendCode = computed(() => {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email) && countdown.value === 0
})

function switchMode(nextMode) {
  mode.value = nextMode
  form.password = ''
  form.confirmPassword = ''
  form.verification_code = ''
  formError.value = ''
}

function startCountdown(seconds) {
  countdown.value = seconds
  if (countdownTimer) window.clearInterval(countdownTimer)
  countdownTimer = window.setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) {
      window.clearInterval(countdownTimer)
      countdownTimer = null
      countdown.value = 0
    }
  }, 1000)
}

async function handleSendCode() {
  if (!canSendCode.value) {
    showFormError('请先输入正确的邮箱', 'warning')
    return
  }

  sendingCode.value = true
  try {
    formError.value = ''
    const data = await sendAuthCode(form.email, mode.value)
    startCountdown(data.resend_after_seconds || 60)
    ElMessage.success('验证码已发送，请查收邮箱')
  } catch (e) {
    const message = e.response?.data?.detail || e.message || '验证码发送失败'
    formError.value = message
    if (!e.__messageShown) {
      ElMessage.error(message)
    }
  } finally {
    sendingCode.value = false
  }
}

function validateForm() {
  if (!form.email.trim()) return '请输入邮箱'
  if (isRegister.value && !form.username.trim()) return '请输入用户名'
  if (!form.password) return '请输入密码'
  if (isRegister.value && form.password.length < 6) return '密码至少 6 位'
  if (isRegister.value && !form.confirmPassword) return '请再次输入密码'
  if (isRegister.value && form.password !== form.confirmPassword) {
    return '两次输入的密码不一致'
  }
  if (!form.verification_code.trim()) return '请输入邮箱验证码'
  return ''
}

function showFormError(message, type = 'error') {
  formError.value = message
  if (type === 'warning') {
    ElMessage.warning(message)
  } else {
    ElMessage.error(message)
  }
}

async function handleSubmit() {
  const error = validateForm()
  if (error) {
    showFormError(error, 'warning')
    return
  }

  loading.value = true
  try {
    formError.value = ''
    const payload = {
      email: form.email.trim(),
      password: form.password,
      verification_code: form.verification_code.trim(),
    }
    if (isRegister.value) {
      payload.username = form.username.trim()
      payload.confirm_password = form.confirmPassword
      await userStore.register(payload)
      ElMessage.success('注册成功')
    } else {
      await userStore.login(payload)
      ElMessage.success('登录成功')
    }
    router.push('/')
  } catch (e) {
    const message = e.response?.data?.detail || e.message || '操作失败，请检查输入信息'
    formError.value = message
    if (!e.__messageShown) {
      ElMessage.error(message)
    }
  } finally {
    loading.value = false
  }
}

onBeforeUnmount(() => {
  if (countdownTimer) window.clearInterval(countdownTimer)
})
</script>

<template>
  <div class="auth-page">
    <section class="auth-hero">
      <p class="eyebrow">FindJobAgent Account</p>
      <h1>{{ title }}</h1>
      <p>{{ subtitle }}</p>
      <div class="trust-row">
        <span><el-icon><CircleCheck /></el-icon> 邮箱验证码</span>
        <span><el-icon><CircleCheck /></el-icon> 本地用户数据</span>
        <span><el-icon><CircleCheck /></el-icon> 预留数据库接入</span>
      </div>
    </section>

    <section class="auth-panel">
      <div class="mode-switch">
        <button :class="{ active: mode === 'login' }" @click="switchMode('login')">
          登录
        </button>
        <button :class="{ active: mode === 'register' }" @click="switchMode('register')">
          注册
        </button>
      </div>

      <transition name="form-rise" mode="out-in">
        <div :key="mode" class="form-stack">
          <el-alert
            v-if="formError"
            class="form-error"
            type="error"
            :title="formError"
            show-icon
            :closable="false"
          />

          <label class="field">
            <span>邮箱</span>
            <el-input v-model="form.email" size="large" placeholder="name@example.com">
              <template #prefix>
                <el-icon><Message /></el-icon>
              </template>
            </el-input>
          </label>

          <label v-if="isRegister" class="field">
            <span>用户名</span>
            <el-input v-model="form.username" size="large" placeholder="请输入用户名">
              <template #prefix>
                <el-icon><User /></el-icon>
              </template>
            </el-input>
          </label>

          <label class="field">
            <span>密码</span>
            <el-input
              v-model="form.password"
              size="large"
              type="password"
              placeholder="请输入密码"
              show-password
              @keyup.enter="handleSubmit"
            >
              <template #prefix>
                <el-icon><Lock /></el-icon>
              </template>
            </el-input>
          </label>

          <label v-if="isRegister" class="field">
            <span>确认密码</span>
            <el-input
              v-model="form.confirmPassword"
              size="large"
              type="password"
              placeholder="请再次输入密码"
              show-password
              @keyup.enter="handleSubmit"
            >
              <template #prefix>
                <el-icon><Lock /></el-icon>
              </template>
            </el-input>
          </label>

          <label class="field">
            <span>邮箱验证码</span>
            <div class="code-line">
              <el-input
                v-model="form.verification_code"
                size="large"
                placeholder="6 位验证码"
                @keyup.enter="handleSubmit"
              />
              <el-button
                class="code-button"
                size="large"
                :loading="sendingCode"
                :disabled="!canSendCode || sendingCode"
                @click="handleSendCode"
              >
                {{ countdown ? `${countdown}s` : '发送验证码' }}
              </el-button>
            </div>
          </label>

          <el-button
            type="primary"
            size="large"
            class="submit-button"
            :loading="loading"
            @click="handleSubmit"
          >
            {{ isRegister ? '注册并进入' : '登录' }}
            <el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
      </transition>
    </section>
  </div>
</template>

<style scoped>
.auth-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 440px);
  gap: 56px;
  align-items: center;
  min-height: calc(100vh - var(--header-height));
  padding: 64px clamp(24px, 6vw, 96px);
  color: #1d1d1f;
  background:
    radial-gradient(circle at 18% 12%, rgba(0, 113, 227, 0.14), transparent 28%),
    radial-gradient(circle at 82% 22%, rgba(125, 91, 255, 0.12), transparent 26%),
    linear-gradient(180deg, #fbfbfd 0%, #f5f5f7 56%, #ffffff 100%);
}

.auth-hero,
.auth-panel {
  animation: auth-rise 0.68s ease both;
}

.auth-panel {
  animation-delay: 0.08s;
}

.eyebrow {
  margin: 0 0 14px;
  color: #6e6e73;
  font-size: 15px;
  font-weight: 600;
}

.auth-hero h1 {
  max-width: 680px;
  margin: 0;
  font-size: clamp(48px, 7vw, 86px);
  font-weight: 700;
  line-height: 1.04;
}

.auth-hero p:not(.eyebrow) {
  max-width: 620px;
  margin: 24px 0 0;
  color: #6e6e73;
  font-size: 21px;
  line-height: 1.55;
}

.trust-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 34px;
}

.trust-row span {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 40px;
  padding: 0 14px;
  border: 1px solid rgba(29, 29, 31, 0.08);
  border-radius: 999px;
  color: #167c3a;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(18px);
}

.auth-panel {
  position: relative;
  padding: 28px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 34px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 36px 80px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(24px);
}

.auth-panel::before {
  position: absolute;
  inset: -50% auto auto -30%;
  width: 70%;
  height: 200%;
  content: '';
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.6), transparent);
  transform: rotate(18deg);
  animation: panel-sheen 5.2s ease-in-out infinite;
}

.mode-switch,
.form-stack {
  position: relative;
  z-index: 1;
}

.mode-switch {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  padding: 6px;
  margin-bottom: 24px;
  border-radius: 999px;
  background: #f5f5f7;
}

.mode-switch button {
  min-height: 42px;
  border: 0;
  border-radius: 999px;
  color: #6e6e73;
  font: inherit;
  font-weight: 700;
  background: transparent;
  cursor: pointer;
  transition: color 0.22s ease, background 0.22s ease, box-shadow 0.22s ease;
}

.mode-switch button.active {
  color: #1d1d1f;
  background: #fff;
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.08);
}

.form-stack {
  display: grid;
  gap: 18px;
}

.form-error {
  border-radius: 16px;
}

.field {
  display: grid;
  gap: 8px;
}

.field span {
  color: #515154;
  font-weight: 700;
}

.code-line {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 132px;
  gap: 10px;
}

.code-button,
.submit-button {
  border-radius: 999px;
  font-weight: 700;
}

.submit-button {
  min-height: 48px;
  margin-top: 4px;
  border-color: #0071e3;
  background: #0071e3;
  box-shadow: 0 16px 38px rgba(0, 113, 227, 0.22);
  transition: transform 0.22s ease, box-shadow 0.22s ease;
}

.submit-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 20px 44px rgba(0, 113, 227, 0.26);
}

:deep(.el-input__wrapper) {
  min-height: 46px;
  border-radius: 16px;
  box-shadow: 0 0 0 1px rgba(29, 29, 31, 0.1) inset;
  transition: box-shadow 0.22s ease, background 0.22s ease;
}

:deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1.5px #0071e3 inset, 0 10px 28px rgba(0, 113, 227, 0.1);
}

.form-rise-enter-active,
.form-rise-leave-active {
  transition: opacity 0.24s ease, transform 0.24s ease;
}

.form-rise-enter-from,
.form-rise-leave-to {
  opacity: 0;
  transform: translateY(12px);
}

@keyframes auth-rise {
  from {
    opacity: 0;
    transform: translateY(18px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes panel-sheen {
  0%,
  45% {
    transform: translateX(-130%) rotate(18deg);
  }
  72%,
  100% {
    transform: translateX(260%) rotate(18deg);
  }
}

@media (max-width: 900px) {
  .auth-page {
    grid-template-columns: 1fr;
    gap: 32px;
    padding: 42px 18px 56px;
  }

  .auth-panel {
    max-width: 520px;
    width: 100%;
    margin: 0 auto;
  }
}

@media (max-width: 520px) {
  .auth-hero h1 {
    font-size: 44px;
  }

  .auth-hero p:not(.eyebrow) {
    font-size: 18px;
  }

  .auth-panel {
    padding: 22px;
    border-radius: 26px;
  }

  .code-line {
    grid-template-columns: 1fr;
  }
}
</style>
