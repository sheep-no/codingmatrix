<template>
  <div class="agent-model-config">
    <h3 class="section-title">Agent 环节模型配置</h3>
    <p class="section-desc">自定义 Agent 不同环节使用的模型。可配置系统内置供应商的 Token，或自定义供应商的模型。</p>
    
    <div class="config-grid">
      <div v-for="(layer, index) in layers" :key="layer.id" class="config-item">
        <div class="config-header">
          <span class="layer-icon">{{ layer.icon }}</span>
          <span class="layer-name">{{ layer.name }}</span>
          <span class="layer-id">{{ layer.id }}</span>
        </div>
        <div class="config-body">
          <select v-model="layerConfig[layer.id]" class="model-select" @change="saveConfig">
            <option value="default">系统默认</option>
            <optgroup label="已配置的 API Key">
              <option v-for="key in availableKeys" :key="key.token" :value="'key:' + key.token" :disabled="!key.enabled || isTokenExpired(key)">
                {{ getProviderName(key.provider) }} - {{ key.remark || '无备注' }}
                {{ !key.enabled ? ' (已禁用)' : '' }}
                {{ isTokenExpired(key) ? ' (已过期)' : '' }}
              </option>
            </optgroup>
            <optgroup label="自定义供应商模型">
              <option v-for="dm in dynamicModels" :key="'dp:' + dm.provider_id + ':' + dm.model_id" :value="'dp:' + dm.provider_id + ':' + dm.model_id">
                {{ dm.provider_name }} / {{ dm.model_id }}
              </option>
            </optgroup>
          </select>
          <span v-if="layerConfig[layer.id] !== 'default'" class="current-key">当前：{{ getCurrentKeyName(layerConfig[layer.id]) }}</span>
        </div>
      </div>
    </div>
    <div class="config-actions">
      <button class="reset-btn" @click="resetToDefault">重置为默认</button>
      <span class="save-hint">配置自动保存</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useApiKeyStore } from '@/stores/apikey'
import { useProviderStore } from '@/stores/providers'

const store = useApiKeyStore()
const providerStore = useProviderStore()

const layers = ref([
  { id: 'decision_layer', name: '决策层', icon: '🧠' },
  { id: 'frontend_exec', name: '执行层前端', icon: '🎨' },
  { id: 'backend_exec', name: '执行层后端', icon: '⚙️' },
  { id: 'architecture', name: '架构设计', icon: '🏗️' },
  { id: 'tough_layer', name: '攻坚层', icon: '💪' },
  { id: 'review', name: '审查层', icon: '🔍' },
  { id: 'fix', name: '修复层', icon: '🔧' },
  { id: 'cross_validation', name: '交叉验证', icon: '✅' },
  { id: 'reflection', name: '反思层', icon: '💭' },
])
const layerConfig = ref({})

const availableKeys = ref([])
const dynamicModels = ref([])

onMounted(() => {
  loadConfig()
  availableKeys.value = store.tokens.filter(k => k.provider !== 'siliconflow')
  dynamicModels.value = providerStore.getAllDynamicModels()
  providerStore.listProviders().then(() => {
    dynamicModels.value = providerStore.getAllDynamicModels()
  }).catch(() => {})
})

function loadConfig() {
  layers.value.forEach(layer => {
    layerConfig.value[layer.id] = store.getModelOverride(layer.id)
  })
}

function saveConfig() {
  layers.value.forEach(layer => {
    const value = layerConfig.value[layer.id]
    store.setModelOverride(layer.id, value === 'default' ? 'default' : value)
  })
}

function resetToDefault() {
  layers.value.forEach(layer => {
    layerConfig.value[layer.id] = 'default'
    store.setModelOverride(layer.id, 'default')
  })
}

function getProviderName(provider) {
  const map = {
    siliconflow: '硅基流动',
    openai: 'OpenAI',
    anthropic: 'Anthropic',
    bailian: '阿里百炼',
    glm: '智谱 GLM',
    deepseek: 'DeepSeek',
  }
  return map[provider] || provider
}

function getCurrentKeyName(value) {
  if (value === 'default') return '系统默认'
  if (value.startsWith('key:')) {
    const token = value.slice(4)
    const key = store.tokens.find(k => k.token === token)
    if (!key) return '未知'
    return `${getProviderName(key.provider)} - ${key.remark || '无备注'}`
  }
  if (value.startsWith('dp:')) {
    const parts = value.slice(3).split(':')
    const providerId = parts[0]
    const modelId = parts.slice(1).join(':')
    const p = providerStore.providers.find(x => x.id === providerId)
    return p ? `${p.name} / ${modelId}` : modelId
  }
  return '未知'
}

function isTokenExpired(tokenObj) {
  if (!tokenObj || !tokenObj.expires_at) return true
  return new Date(tokenObj.expires_at) < new Date()
}
</script>

<style scoped>
.agent-model-config { padding: 20px; max-width: 900px; margin: 0 auto; }
.section-title { font-size: 18px; margin-bottom: 8px; }
.section-desc { font-size: 14px; color: #606266; margin-bottom: 24px; }
.config-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
.config-item { border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; background: #fff; }
.config-header { display: flex; align-items: center; gap: 8px; padding: 12px 16px; background: #f5f7fa; border-bottom: 1px solid #e0e0e0; }
.layer-icon { font-size: 20px; }
.layer-name { font-weight: 600; flex: 1; }
.layer-id { font-size: 12px; color: #909399; font-family: monospace; }
.config-body { padding: 16px; }
.model-select { width: 100%; padding: 8px 12px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 14px; margin-bottom: 8px; }
.model-select:disabled { background: #f5f7fa; cursor: not-allowed; }
.current-key { display: block; font-size: 13px; color: #67c23a; }
.config-actions { display: flex; justify-content: center; align-items: center; gap: 16px; padding: 16px; background: #f5f7fa; border-radius: 8px; }
.reset-btn { padding: 8px 20px; background: #909399; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
.reset-btn:hover { background: #606266; }
.save-hint { font-size: 13px; color: #909399; }
</style>
