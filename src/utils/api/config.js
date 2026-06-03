/**
 * API 配置常量
 */
const getWsBaseUrl = () => {
  if (import.meta.env.VITE_WS_BASE) return import.meta.env.VITE_WS_BASE
  const { protocol, host } = window.location
  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProtocol}//${host}`
}

export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_API_BASE || '/api/v1',
  V2_API_URL: '/api/v2',
  WS_BASE_URL: getWsBaseUrl(),
  DEFAULT_PORT: 8000
}

export default API_CONFIG
