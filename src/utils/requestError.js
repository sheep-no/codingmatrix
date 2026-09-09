const STATUS_MESSAGES = Object.freeze({
  401: { kind: 'auth', message: '登录状态已失效，请重新登录后重试。', action: '重新登录' },
  403: { kind: 'permission', message: '当前账号没有执行此模型调用的权限。', action: '检查权限' },
  404: { kind: 'model', message: '请求的模型或服务地址不存在，请检查模型配置。', action: '检查模型' },
  429: { kind: 'rate_limit', message: '请求过于频繁或服务额度已用尽，请稍后重试。', action: '稍后重试' }
})

function getStatus(error) {
  return Number(error?.status || error?.statusCode || error?.response?.status || error?.code) || 0
}

function sanitizeDetail(value) {
  return String(value || '')
    .replace(/bearer\s+[a-z0-9._~-]+/gi, 'Bearer [已隐藏]')
    .replace(/(api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+/gi, '$1=[已隐藏]')
}

export function normalizeRequestError(error, fallback = '请求失败') {
  const status = getStatus(error)
  const known = STATUS_MESSAGES[status]
  const rawMessage = sanitizeDetail(error?.message || (typeof error === 'string' ? error : ''))

  if (known) return { ...known, status, detail: rawMessage, retryable: status !== 401 && status !== 403 }

  const isAbort = error?.name === 'AbortError' || error?.code === 'ERR_CANCELED'
  if (isAbort) return { kind: 'aborted', status: 0, message: '请求已停止。', action: null, detail: rawMessage, retryable: false }

  const isNetwork = error?.name === 'TypeError' || error?.name === 'NetworkError' || /network|fetch|failed to fetch|连接|超时/i.test(rawMessage)
  if (isNetwork) return { kind: 'network', status: 0, message: '网络连接失败，请检查网络后重试。', action: '重新连接', detail: rawMessage, retryable: true }

  return { kind: 'unknown', status, message: rawMessage || fallback, action: '重试', detail: rawMessage, retryable: true }
}

export function getRequestErrorMessage(error, fallback = '请求失败') {
  const normalized = normalizeRequestError(error, fallback)
  return normalized.detail && normalized.detail !== normalized.message
    ? `${normalized.message}（${normalized.detail}）`
    : normalized.message
}
