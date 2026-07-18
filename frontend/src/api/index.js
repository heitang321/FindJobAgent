import request from './request'

/** 健康检查 */
export const checkHealth = () => request.get('/health')

/** 获取当前用户信息 */
export const getUserInfo = () => request.get('/auth/me')

/** 触发 Agent 3 简历优化 */
export const triggerOptimization = (taskId) => request.post(`/optimize/${taskId}`)

/** 获取优化结果、逐段 diff 和优化摘要 */
export const getOptimizationResult = (taskId) =>
  request.get(`/optimize/${taskId}/result`)

/** 下载优化后的 Word 简历 */
export const downloadOptimizedResume = (taskId) =>
  request.get(`/optimize/${taskId}/download`, { responseType: 'blob' })
