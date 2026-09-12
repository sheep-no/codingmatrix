/**
 * API Key 管理 API 请求封装
 */
import { api } from '@/utils/api/index'

function errorMessage(data, fallback) {
  const detail = data?.detail ?? data?.message
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return fallback
}

async function requestJson(method, url, body) {
  if (typeof api.request !== 'function') {
    throw new Error('API 客户端未初始化')
  }

  const options = { method }
  if (body !== undefined) {
    options.body = JSON.stringify(body)
  }

  const response = await api.request(url, options)
  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { message: text }
    }
  }

  if (!response.ok) {
    throw new Error(errorMessage(data, `请求失败 (${response.status})`))
  }
  return data
}

/**
 * 获取 RSA 公钥
 * @returns {Promise<{public_key: string}>}
 */
export async function getPublicKey() {
  return requestJson('GET', '/api/v1/agent/apikey/public-key')
}

/**
 * 提交加密的 API Key
 * @param {Object} data 
 * @param {string} data.provider - 供应商名称
 * @param {string} data.encrypted_key - RSA 加密后的 Key
 * @param {number} data.ttl - TTL 秒数
 * @param {string} data.remark - 备注
 * @returns {Promise<{token: string, provider: string, expires_at: string}>}
 */
export async function submitApiKey(data) {
  return requestJson('POST', '/api/v1/agent/apikey', data)
}

/**
 * 测试 API Key
 * @param {string} token - Key 的 Token
 * @returns {Promise<{success: boolean, message: string}>}
 */
export async function testApiKey(token) {
  return requestJson('POST', '/api/v1/agent/apikey/test', { token })
}

/**
 * 删除 API Key
 * @param {string} token - Key 的 Token
 * @returns {Promise<{message: string}>}
 */
export async function deleteApiKey(token) {
  return requestJson('DELETE', `/api/v1/agent/apikey/${token}`)
}

/**
 * 获取 API Key 列表
 * @returns {Promise<Array<{token: string, provider: string, remark: string, status: string, created_at: string, expires_at: string, ttl_seconds: number, enabled: boolean}>>}
 */
export async function listApiKeys() {
  return requestJson('GET', '/api/v1/agent/apikeys')
}

/**
 * 启用/禁用 API Key
 * @param {string} token - Key 的 Token
 * @param {boolean} enabled - 是否启用
 * @returns {Promise<{message: string}>}
 */
export async function updateApiKeyEnabled(token, enabled) {
  return requestJson(
    'PUT',
    `/api/v1/agent/apikey/${token}/enabled?enabled=${enabled ? 'true' : 'false'}`
  )
}

/**
 * 更新 API Key 的模型 context_length 配置
 * @param {string} token - Key 的 Token
 * @param {Object} context_lengths - 模型 context_length 配置 {model_id: context_length}
 * @returns {Promise<{message: string, context_lengths: Object}>}
 */
export async function updateApiKeyContextLengths(token, context_lengths) {
  return requestJson('PUT', `/api/v1/agent/apikey/${token}/context-lengths`, { context_lengths })
}

/**
 * 批量导入 API Key
 * @param {Array<{provider: string, encrypted_key: string, ttl: string, remark: string}>} keys
 * @returns {Promise<{success_count: number, failed_count: number, results: Array}>}
 */
export async function batchImport(keys) {
  return requestJson('POST', '/api/v1/agent/apikey/batch/import', { keys })
}

/**
 * 批量导出 API Key
 * @param {string} format - 导出格式 (json|csv)
 * @returns {Promise<{format: string, data: string, count: number}>}
 */
export async function batchExport(format = 'json') {
  const query = new URLSearchParams({ format }).toString()
  return requestJson('GET', `/api/v1/agent/apikey/batch/export?${query}`)
}
