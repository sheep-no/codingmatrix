/**
 * Dynamic Provider Store (Pinia)
 * 
 * 管理自定义供应商（自定义 base_url + 协议类型）
 * 支持 OpenAI 兼容协议和 Anthropic 原生协议
 * 自动拉取模型列表
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/utils/api/index'

const STORAGE_KEY = 'codingmatrix_providers'

export const useProviderStore = defineStore('providers', () => {
  const providers = ref([])
  const loading = ref(false)

  // 从 localStorage 加载缓存（用于离线显示）
  function loadFromStorage() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        providers.value = JSON.parse(stored)
      }
    } catch (e) {
      console.error('Load providers from storage failed:', e)
    }
  }

  // 保存到 localStorage 缓存
  function saveToStorage() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(providers.value))
  }

  async function listProviders() {
    try {
      const resp = await api.get('/providers')
      if (!resp.ok) {
        throw new Error(`加载供应商失败 (${resp.status})`)
      }
      const data = await resp.json()
      providers.value = Array.isArray(data) ? data : []
      saveToStorage()
      return providers.value
    } catch (e) {
      console.error('List providers failed:', e)
      throw e
    }
  }

  async function addProvider(data) {
    loading.value = true
    try {
      const resp = await api.post('/providers', data)
      if (!resp.ok) {
        throw new Error(await getResponseError(resp, '添加供应商失败'))
      }
      const result = await resp.json()
      await listProviders()
      return result
    } finally {
      loading.value = false
    }
  }

  async function deleteProvider(id) {
    try {
      const resp = await api.delete(`/providers/${id}`)
      if (!resp.ok) {
        throw new Error(await getResponseError(resp, '删除供应商失败'))
      }
      providers.value = providers.value.filter(p => p.id !== id)
      saveToStorage()
    } catch (e) {
      console.error('Delete provider failed:', e)
      throw e
    }
  }

  async function toggleProvider(id) {
    try {
      const resp = await api.put(`/providers/${id}/toggle`)
      if (!resp.ok) {
        throw new Error(await getResponseError(resp, '更新供应商状态失败'))
      }
      const result = await resp.json()
      const p = providers.value.find(x => x.id === id)
      if (p) {
        p.enabled = result.enabled
      }
      saveToStorage()
    } catch (e) {
      console.error('Toggle provider failed:', e)
      throw e
    }
  }

  async function syncModels(id, force = false) {
    loading.value = true
    try {
      const resp = await api.post(`/providers/${id}/sync?force=${force}`)
      if (!resp.ok) {
        throw new Error(await getResponseError(resp, '同步模型失败'))
      }
      const result = await resp.json()
      if (result.count > 0 && !result.error) {
        await listProviders()
      }
      return result
    } finally {
      loading.value = false
    }
  }

  async function testProvider(id) {
    loading.value = true
    try {
      const resp = await api.post(`/providers/${id}/test`)
      if (!resp.ok) {
        throw new Error(await getResponseError(resp, '测试供应商失败'))
      }
      return await resp.json()
    } finally {
      loading.value = false
    }
  }

  async function getResponseError(resp, fallback) {
    try {
      const payload = await resp.json()
      return payload.detail || payload.message || fallback
    } catch {
      return fallback
    }
  }

  /**
   * 获取所有启用的动态供应商的模型列表
   * 返回格式: [{ provider_name, model_id, protocol }, ...]
   */
  function getAllDynamicModels() {
    const result = []
    const seen = new Set()
    for (const p of providers.value) {
      if (!p.enabled) continue
      for (const modelObj of (p.models || [])) {
        const modelId = typeof modelObj === 'string' ? modelObj : modelObj.id
        if (!modelId) continue
        const key = `${p.id}::${modelId}`
        if (seen.has(key)) continue
        seen.add(key)
        result.push({
          provider_name: p.name,
          model_id: modelId,
          protocol: p.protocol,
          provider_id: p.id,
          context_length: typeof modelObj === 'object' ? modelObj.context_length : undefined,
        })
      }
    }
    return result.sort((a, b) => {
      const providerOrder = a.provider_name.localeCompare(b.provider_name)
      return providerOrder || a.model_id.localeCompare(b.model_id)
    })
  }

  return {
    providers,
    loading,
    loadFromStorage,
    listProviders,
    addProvider,
    deleteProvider,
    toggleProvider,
    syncModels,
    testProvider,
    getAllDynamicModels,
  }
})
