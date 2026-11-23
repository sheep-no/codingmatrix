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

// 从后端错误响应体里取可直接展示的文案，兼容 message/detail 字符串与
// FastAPI 校验错误数组。取不到时返回空串，由调用方回退到状态码兜底文案。
export function extractApiErrorMessage(payload) {
  if (!payload) return ''
  if (typeof payload === 'string') return payload.trim()

  const direct = [payload.message, payload.detail]
  for (const value of direct) {
    if (typeof value === 'string' && value.trim()) return value.trim()
  }

  const detail = payload.detail
  if (Array.isArray(detail)) {
    return detail
      .map(item => (typeof item === 'string' ? item : item?.msg))
      .filter(Boolean)
      .join('；')
  }
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
    return detail.message
  }
  return ''
}

export function isTransportPlaceholder(message) {
  return /^HTTP error! status: \d+$/i.test(message) || /^HTTP\s+\d+$/i.test(message)
}

export function normalizeRequestError(error, fallback = '请求失败') {
  const status = getStatus(error)
  const known = STATUS_MESSAGES[status]
  const rawMessage = sanitizeDetail(error?.message || (typeof error === 'string' ? error : ''))
  const readableMessage = isTransportPlaceholder(rawMessage) ? '' : rawMessage

  if (known) {
    const message = readableMessage ? `${known.message}（${readableMessage}）` : known.message
    return {
      ...known,
      message,
      status,
      detail: readableMessage,
      retryable: status !== 401 && status !== 403
    }
  }

  const isAbort = error?.name === 'AbortError' || error?.code === 'ERR_CANCELED'
  if (isAbort) return { kind: 'aborted', status: 0, message: '请求已停止。', action: null, detail: readableMessage, retryable: false }

  // 有 HTTP 状态码时以服务端文案为准；只有拿不到状态才按传输层失败归类，
  // 否则「生成超时」这类后端文案会被通用网络提示覆盖。
  const isNetwork = status === 0 && (
    error?.name === 'TypeError'
    || error?.name === 'NetworkError'
    || /network|fetch|failed to fetch|连接|超时/i.test(rawMessage)
  )
  if (isNetwork) return { kind: 'network', status: 0, message: '网络连接失败，请检查网络后重试。', action: '重新连接', detail: readableMessage, retryable: true }

  return { kind: 'unknown', status, message: readableMessage || fallback, action: '重试', detail: readableMessage, retryable: true }
}

export function getRequestErrorMessage(error, fallback = '请求失败') {
  return normalizeRequestError(error, fallback).message
}

// 历史消息可能残留旧版本写入的「出错：HTTP error! status: 400」。
// 这类传输层占位串对用户没有信息量，展示前按行剔除。
export function stripTransportPlaceholderLines(text) {
  if (typeof text !== 'string' || !text) return text || ''
  return text
    .split('\n')
    .filter(line => !isTransportPlaceholder(line.replace(/^\s*(出错：|失败：)?\s*/, '').trim()))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
