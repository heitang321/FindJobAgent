import request from './request'

/** 健康检查 */
export const checkHealth = () => request.get('/health')

/** 获取当前用户信息 */
export const getUserInfo = () => request.get('/auth/me')

/** 发送登录 / 注册邮箱验证码 */
export const sendAuthCode = (email, purpose) =>
  request.post('/auth/send-code', { email, purpose })

/** 邮箱验证码注册 */
export const registerWithEmail = (payload) => request.post('/auth/register', payload)

/** 邮箱验证码登录 */
export const loginWithEmail = (payload) => request.post('/auth/login', payload)

/** 获取当前用户的简历任务历史列表 */
export const getResumeHistory = () => request.get('/resume/history')

/** 上传简历并启动 Agent 1 分析（异步后台执行） */
export const uploadResume = (file) => {
  const form = new FormData()
  form.append('file', file)
  return request.post('/resume/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 查询 Agent 1 简历结构化分析结果（轮询用） */
export const getResumeAnalysis = (taskId) =>
  request.get(`/resume/${taskId}/analysis`)

/** 提交 JD URL，同步执行 Agent 2（抓取 JD → 结构化 → 匹配 → 差距分析） */
export const submitJdUrl = (taskId, jdUrl) =>
  request.post(`/job/${taskId}/analyze`, { jd_url: jdUrl })

/** 触发 Agent 3 简历优化 */
export const triggerOptimization = (taskId) => request.post(`/optimize/${taskId}`)

/** 获取优化结果、逐段对比和优化摘要 */
export const getOptimizationResult = (taskId) =>
  request.get(`/optimize/${taskId}/result`)

/** 下载优化后的 Word 简历 */
export const downloadOptimizedResume = (taskId) =>
  request.get(`/optimize/${taskId}/download`, { responseType: 'blob' })
