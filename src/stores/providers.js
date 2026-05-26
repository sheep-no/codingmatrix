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
      providers.value = await resp.json()
      saveToStorage()
      return providers.value
    } catch (e) {
      console.error('List providers failed:', e)
      return []
    }
  }

  async function addProvider(data) {
    loading.value = true
    try {
      const resp = await api.post('/providers', data)
      const result = await resp.json()
      await listProviders()
      return result
    } finally {
      loading.value = false
    }
  }

  async function deleteProvider(id) {
    try {
      await api.delete(`/providers/${id}`)
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
      return await resp.json()
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取所有启用的动态供应商的模型列表
   * 返回格式: [{ provider_name, model_id, protocol }, ...]
   */
  function getAllDynamicModels() {
    const result = []
    for (const p of providers.value) {
      if (!p.enabled) continue
      for (const modelObj of (p.models || [])) {
        const modelId = typeof modelObj === 'string' ? modelObj : modelObj.id
        result.push({
          provider_name: p.name,
          model_id: modelId,
          protocol: p.protocol,
          provider_id: p.id,
        })
      }
    }
    return result
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
