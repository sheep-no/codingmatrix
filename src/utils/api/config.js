/**
 * API 配置常量
 */
export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_API_BASE || '/api/v1',
  V2_API_URL: '/api/v2',
  WS_BASE_URL: import.meta.env.VITE_WS_BASE || 'ws://127.0.0.1:8080',
  DEFAULT_PORT: 8080
}

export default API_CONFIG
