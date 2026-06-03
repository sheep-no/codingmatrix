/**
 * API Key 状态管理 (Pinia)
 * 
 * 管理用户的 API Key Token 列表、RSA 公钥、Agent 模型配置
 * 数据持久化到 localStorage（仅存 Token 和元数据，不存 Key）
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getPublicKey, submitApiKey, testApiKey, deleteApiKey, listApiKeys, updateApiKeyEnabled, updateApiKeyContextLengths } from '@/api/apikey'
import { encryptWithRSAPublicKey } from '@/utils/crypto'

const STORAGE_KEY = 'codingmatrix_apikeys'
const STORAGE_PUBLIC_KEY = 'codingmatrix_rsa_public_key'
const STORAGE_MODEL_OVERRIDES = 'codingmatrix_model_overrides'

export const useApiKeyStore = defineStore('apikey', () => {
  // State
  const tokens = ref([])
  const publicKey = ref('')
  const modelOverrides = ref({})
  const loading = ref(false)

  // Computed
  const siliconflowKey = computed(() => {
    return tokens.value.find(t => t.provider === 'siliconflow')
  })

  const otherKeys = computed(() => {
    return tokens.value.filter(t => t.provider !== 'siliconflow')
  })

  const hasSiliconflowKey = computed(() => {
    return !!siliconflowKey.value && siliconflowKey.value.enabled
  })

  // Actions
  /**
   * 从 localStorage 加载数据
   */
  function loadFromStorage() {
    try {
      const storedTokens = localStorage.getItem(STORAGE_KEY)
      if (storedTokens) {
        tokens.value = JSON.parse(storedTokens)
      }
      
      const storedPublicKey = localStorage.getItem(STORAGE_PUBLIC_KEY)
      if (storedPublicKey) {
        publicKey.value = storedPublicKey
      }

      const storedOverrides = localStorage.getItem(STORAGE_MODEL_OVERRIDES)
      if (storedOverrides) {
        modelOverrides.value = JSON.parse(storedOverrides)
      }
    } catch (e) {
      console.error('加载 API Key 数据失败：', e)
    }
  }

  /**
   * 保存 tokens 到 localStorage
   */
  function saveTokens() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens.value))
  }

  /**
   * 保存公钥到 localStorage
   */
  function savePublicKey(key) {
    publicKey.value = key
    localStorage.setItem(STORAGE_PUBLIC_KEY, key)
  }

  /**
   * 保存模型配置到 localStorage
   */
  function saveModelOverrides() {
    localStorage.setItem(STORAGE_MODEL_OVERRIDES, JSON.stringify(modelOverrides.value))
  }

  /**
   * 获取 RSA 公钥
   */
  async function fetchPublicKey() {
    if (publicKey.value) {
      return publicKey.value
    }
    
    try {
      const response = await getPublicKey()
      savePublicKey(response.public_key)
      return response.public_key
    } catch (e) {
      console.error('获取公钥失败：', e)
      throw e
    }
  }

  /**
   * 提交 API Key
   */
  async function submitKey(provider, rawKey, ttl, remark = '') {
    loading.value = true
    try {
      // 获取公钥
      const pubKey = await fetchPublicKey()
      
      // 加密 Key
      const encryptedKey = await encryptWithRSAPublicKey(rawKey, pubKey)
      
      // 提交到后端（ttl 现在是秒数整数）
      const response = await submitApiKey({
        provider,
        encrypted_key: encryptedKey,
        ttl: typeof ttl === 'number' ? ttl : getTTLSeconds(ttl),
        remark,
      })
      
      // 添加到本地列表
      const newToken = {
        token: response.token,
        provider: response.provider,
        remark,
        status: 'unverified',
        created_at: new Date().toISOString(),
        expires_at: response.expires_at,
        ttl_seconds: typeof ttl === 'number' ? ttl : getTTLSeconds(ttl),
        enabled: true,
      }
      tokens.value.unshift(newToken)
      saveTokens()
      
      return response
    } finally {
      loading.value = false
    }
  }

  /**
   * 测试 API Key
   */
  async function testKey(token) {
    try {
      const response = await testApiKey(token)
      
      // 更新本地状态
      const index = tokens.value.findIndex(t => t.token === token)
      if (index !== -1) {
        tokens.value[index].status = response.success ? 'verified' : 'invalid'
        saveTokens()
      }
      
      return response
    } catch (e) {
      console.error('测试 Key 失败：', e)
      throw e
    }
  }

  /**
   * 删除 API Key
   */
  async function deleteKey(token) {
    try {
      await deleteApiKey(token)
      
      // 从本地列表移除
      tokens.value = tokens.value.filter(t => t.token !== token)
      saveTokens()
    } catch (e) {
      console.error('删除 Key 失败：', e)
      throw e
    }
  }

  /**
   * 获取 API Key 列表（从后端同步）
   */
  async function listKeys() {
    try {
      const response = await listApiKeys()
      tokens.value = response
      saveTokens()
      return response
    } catch (e) {
      console.error('获取 Key 列表失败：', e)
      throw e
    }
  }

  /**
   * 启用/禁用 API Key
   */
  async function toggleEnabled(token, enabled) {
    try {
      await updateApiKeyEnabled(token, enabled)
      
      // 更新本地状态
      const index = tokens.value.findIndex(t => t.token === token)
      if (index !== -1) {
        tokens.value[index].enabled = enabled
        saveTokens()
      }
    } catch (e) {
      console.error('更新 Key 状态失败：', e)
      throw e
    }
  }

  /**
   * 更新 API Key 的模型 context_length 配置
   */
  async function updateContextLengths(token, context_lengths) {
    try {
      const result = await updateApiKeyContextLengths(token, context_lengths)
      
      // 更新本地状态
      const index = tokens.value.findIndex(t => t.token === token)
      if (index !== -1) {
        tokens.value[index].context_lengths = result.context_lengths || {}
        saveTokens()
      }
      return result
    } catch (e) {
      console.error('更新 context_lengths 失败：', e)
      throw e
    }
  }

  /**
   * 设置环节模型配置
   */
  function setModelOverride(layer, token) {
    modelOverrides.value[layer] = token
    saveModelOverrides()
  }

  /**
   * 获取环节对应的 Token
   */
  function getModelOverride(layer) {
    return modelOverrides.value[layer] || 'default'
  }

  /**
   * 获取所有环节配置（用于 Agent 请求）
   */
  function getUserModelOverrides() {
    return { ...modelOverrides.value }
  }

  /**
   * 检查 Token 是否过期
   */
  function isTokenExpired(tokenObj) {
    if (!tokenObj || !tokenObj.expires_at) return true
    const expiresAt = new Date(tokenObj.expires_at)
    return expiresAt < new Date()
  }

  // Helper
  function getTTLSeconds(ttl) {
    const ttlMap = {
      '1h': 3600,
      '24h': 86400,
      '7d': 604800,
      '30d': 2592000,
      'never': 315360000,  // 10 年，近似永久
    }
    // 如果是数字直接返回（自定义秒数）
    if (typeof ttl === 'number') {
      return ttl
    }
    return ttlMap[ttl] || 86400
  }

  return {
    // State
    tokens,
    publicKey,
    modelOverrides,
    loading,
    
    // Computed
    siliconflowKey,
    otherKeys,
    hasSiliconflowKey,
    
    // Actions
    loadFromStorage,
    fetchPublicKey,
    submitKey,
    testKey,
    deleteKey,
    listKeys,
    toggleEnabled,
    setModelOverride,
    getModelOverride,
    getUserModelOverrides,
    isTokenExpired,
  }
})
