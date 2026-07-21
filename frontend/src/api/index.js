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

/** 删除指定的简历任务记录 */
export const deleteResumeTask = (taskId) => request.delete(`/resume/${taskId}`)

/** 上传并保存简历；Agent 1 在提交 JD 或自动推荐时按需执行 */
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

/** 根据简历内容自动检索 zhaopin 岗位，返回岗位卡片列表供用户选择
 *  keywords 留空时后端从简历 skills 自动推导
 */
export const searchJobs = (taskId, { keywords = '', city = '', maxResults = 10 } = {}) =>
  request.post(`/job/${taskId}/search`, {
    keywords: keywords || null,
    city,
    max_results: maxResults,
  })

/** 触发 Agent 3 简历优化 */
export const triggerOptimization = (taskId) => request.post(`/optimize/${taskId}`)

/** 获取优化结果、逐段对比和优化摘要 */
export const getOptimizationResult = (taskId) =>
  request.get(`/optimize/${taskId}/result`)

/** 智能问答（支持会话持久化） */
export const sendChat = (question, context = '', sessionId = null) =>
  request.post('/chat/chat', { question, context, session_id: sessionId })

/** 获取用户的聊天会话列表 */
export const getChatSessions = () =>
  request.get('/chat/sessions')

/** 获取指定会话的所有消息 */
export const getChatMessages = (sessionId) =>
  request.get(`/chat/sessions/${sessionId}/messages`)

/** 删除指定会话 */
export const deleteChatSession = (sessionId) =>
  request.delete(`/chat/sessions/${sessionId}`)

/** 下载优化后的 Word 简历 */
export const downloadOptimizedResume = (taskId) =>
  request.get(`/optimize/${taskId}/download`, { responseType: 'blob' })


