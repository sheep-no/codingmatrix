/**
 * API Key 管理 API 请求封装
 */
import request from '@/utils/request'

/**
 * 获取 RSA 公钥
 * @returns {Promise<{public_key: string}>}
 */
export async function getPublicKey() {
  const response = await request.get('/api/v1/agent/apikey/public-key')
  return response.data
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
  const response = await request.post('/api/v1/agent/apikey', data)
  return response.data
}

/**
 * 测试 API Key
 * @param {string} token - Key 的 Token
 * @returns {Promise<{success: boolean, message: string}>}
 */
export async function testApiKey(token) {
  const response = await request.post('/api/v1/agent/apikey/test', { token })
  return response.data
}

/**
 * 删除 API Key
 * @param {string} token - Key 的 Token
 * @returns {Promise<{message: string}>}
 */
export async function deleteApiKey(token) {
  const response = await request.delete(`/api/v1/agent/apikey/${token}`)
  return response.data
}

/**
 * 获取 API Key 列表
 * @returns {Promise<Array<{token: string, provider: string, remark: string, status: string, created_at: string, expires_at: string, ttl_seconds: number, enabled: boolean}>>}
 */
export async function listApiKeys() {
  const response = await request.get('/api/v1/agent/apikeys')
  return response.data
}

/**
 * 启用/禁用 API Key
 * @param {string} token - Key 的 Token
 * @param {boolean} enabled - 是否启用
 * @returns {Promise<{message: string}>}
 */
export async function updateApiKeyEnabled(token, enabled) {
  const response = await request.put(`/api/v1/agent/apikey/${token}/enabled`, { enabled })
  return response.data
}

/**
 * 更新 API Key 的模型 context_length 配置
 * @param {string} token - Key 的 Token
 * @param {Object} context_lengths - 模型 context_length 配置 {model_id: context_length}
 * @returns {Promise<{message: string, context_lengths: Object}>}
 */
export async function updateApiKeyContextLengths(token, context_lengths) {
  const response = await request.put(`/api/v1/agent/apikey/${token}/context-lengths`, { context_lengths })
  return response.data
}

/**
 * 批量导入 API Key
 * @param {Array<{provider: string, encrypted_key: string, ttl: string, remark: string}>} keys
 * @returns {Promise<{success_count: number, failed_count: number, results: Array}>}
 */
export async function batchImport(keys) {
  const response = await request.post('/api/v1/agent/apikey/batch/import', { keys })
  return response.data
}

/**
 * 批量导出 API Key
 * @param {string} format - 导出格式 (json|csv)
 * @returns {Promise<{format: string, data: string, count: number}>}
 */
export async function batchExport(format = 'json') {
  const response = await request.get('/api/v1/agent/apikey/batch/export', { params: { format } })
  return response.data
}
