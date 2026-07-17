import request from './request'

/** 健康检查 */
export const checkHealth = () => request.get('/health')

/** 获取当前用户信息 */
export const getUserInfo = () => request.get('/auth/me')
