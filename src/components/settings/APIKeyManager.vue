<template>
  <div class="api-key-manager">
    <h2 class="section-title">API Key 管理</h2>
    
    <!-- 硅基流动 Key (必填) -->
    <div class="key-card required-key">
      <div class="key-card-header">
        <svg class="provider-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
        <span class="provider-name">硅基流动 (SiliconFlow)</span>
        <span class="required-badge">必填</span>
        <span :class="['status-badge', siliconflowKey?.status || 'unverified']">
          {{ getStatusText(siliconflowKey?.status) }}
        </span>
      </div>
      
      <div v-if="!siliconflowKey" class="key-card-body">
        <p class="guide-text">
          配置硅基流动 API Key 以使用 Agent 功能。
          <a href="https://cloud.siliconflow.cn/" target="_blank" class="guide-link">前往注册</a>
        </p>
        <div class="add-key-form">
          <input v-model="siliconflowForm.key" type="password" placeholder="输入 API Key" class="key-input" />
          <select v-model="siliconflowForm.ttl" class="ttl-select" @change="onTTLChange(siliconflowForm)">
            <option value="24h">24 小时</option>
            <option value="7d">7 天</option>
            <option value="30d">30 天</option>
            <option value="never">永远</option>
            <option value="custom">自定义</option>
          </select>
          <input v-if="siliconflowForm.ttl === 'custom'" v-model.number="siliconflowForm.customHours" type="number" min="1" placeholder="小时数" class="custom-ttl-input" />
          <button :disabled="loading" class="submit-btn" @click="submitSiliconflowKey">
            {{ loading ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
      
      <div v-else class="key-card-body">
        <div class="key-info">
          <span class="key-remark">{{ siliconflowKey.remark || '主 Key' }}</span>
          <span class="key-expiry">剩余：{{ getRemainingTime(siliconflowKey) }}</span>
        </div>
        <div class="key-actions">
          <button class="action-btn test-btn" @click="testKey(siliconflowKey.token)">测试连接</button>
          <button class="action-btn delete-btn" @click="deleteKey(siliconflowKey.token)">清除</button>
        </div>
      </div>
    </div>
    
    <!-- 其他供应商 Key -->
    <div class="other-keys-section">
      <h3 class="subsection-title">其他供应商 (可选)</h3>
      
      <!-- 添加新 Key 表单 -->
      <div class="add-key-form-expanded">
        <select v-model="newKeyForm.provider" class="provider-select">
          <option value="">选择供应商</option>
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
          <option value="bailian">阿里百炼</option>
          <option value="glm">智谱 GLM</option>
          <option value="deepseek">DeepSeek</option>
        </select>
        <input v-model="newKeyForm.key" type="password" placeholder="输入 API Key" class="key-input" />
        <input v-model="newKeyForm.remark" type="text" placeholder="备注 (可选)" class="remark-input" />
        <select v-model="newKeyForm.ttl" class="ttl-select" @change="onTTLChange(newKeyForm)">
          <option value="1h">1 小时</option>
          <option value="24h">24 小时</option>
          <option value="7d">7 天</option>
          <option value="30d">30 天</option>
          <option value="never">永远</option>
          <option value="custom">自定义</option>
        </select>
        <input v-if="newKeyForm.ttl === 'custom'" v-model.number="newKeyForm.customHours" type="number" min="1" placeholder="小时数" class="custom-ttl-input" />
        <button :disabled="loading || !newKeyForm.provider || !newKeyForm.key" class="submit-btn" @click="submitNewKey">
          {{ loading ? '添加中...' : '添加' }}
        </button>
      </div>
      
      <!-- Key 列表 -->
      <div v-if="otherKeys.length > 0" class="key-list">
        <div v-for="key in otherKeys" :key="key.token" class="key-card">
          <div class="key-card-header">
            <svg class="provider-icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
            <span class="provider-name">{{ getProviderName(key.provider) }}</span>
            <span :class="['status-badge', key.status]">
              {{ getStatusText(key.status) }}
            </span>
          </div>
          <div class="key-card-body">
            <div class="key-info">
              <span class="key-remark">{{ key.remark || '-' }}</span>
              <span class="key-expiry">剩余：{{ getRemainingTime(key) }}</span>
            </div>
            <div class="key-actions">
              <button class="action-btn test-btn" @click="testKey(key.token)">测试</button>
              <button class="action-btn toggle-btn" @click="toggleEnabled(key)">
                {{ key.enabled ? '禁用' : '启用' }}
              </button>
              <button class="action-btn config-btn" @click="toggleContextConfig(key.token)">
                {{ expandedContextConfig === key.token ? '收起' : '模型配置' }}
              </button>
              <button class="action-btn config-btn" @click="toggleFallbackConfig(key.token)">
                {{ expandedFallbackConfig === key.token ? '收起' : '降级链' }}
              </button>
              <button class="action-btn delete-btn" @click="deleteKey(key.token)">清除</button>
            </div>
          </div>
          <!-- 模型 context_length 配置 -->
          <div v-if="expandedContextConfig === key.token" class="context-config-section">
            <div class="context-config-header">
              <span class="context-config-title">模型上下文长度配置</span>
              <span class="context-config-hint">设置模型的最大上下文长度（token）</span>
            </div>
            <div class="context-config-list">
              <div v-for="(ctx, model) in key.context_lengths || {}" :key="model" class="context-config-item">
                <span class="model-name">{{ model }}</span>
                <input
                  v-model.number="key.context_lengths[model]"
                  type="number"
                  min="1"
                  class="context-input"
                  placeholder="context length"
                />
                <span class="context-unit">tokens</span>
                <button class="action-btn delete-btn" @click="removeContextLength(key, model)">删除</button>
              </div>
              <div v-if="!key.context_lengths || Object.keys(key.context_lengths).length === 0" class="empty-context">
                暂无自定义配置，将使用默认值 32k
              </div>
            </div>
            <div class="context-config-add">
              <input v-model="newContextLengths[key.token].model" type="text" placeholder="模型名称 (如 gpt-4o)" class="context-input model-input" />
              <input v-model.number="newContextLengths[key.token].value" type="number" min="1" placeholder="context length" class="context-input" />
              <button class="action-btn" @click="addContextLength(key)">添加</button>
              <button class="action-btn save-btn" @click="saveContextLengths(key)">保存全部</button>
            </div>
          </div>
          <!-- 降级链配置 -->
          <div v-if="expandedFallbackConfig === key.token" class="context-config-section">
            <div class="context-config-header">
              <span class="context-config-title">降级链配置</span>
              <span class="context-config-hint">当首选模型不可用时的降级策略</span>
            </div>
            <div class="fallback-preference-select">
              <select
                :value="key.fallback_preference || 'use_admin_default'"
                class="model-select"
                @change="updateFallbackPreference(key, $event.target.value)"
              >
                <option value="use_admin_default">使用管理员默认降级链</option>
                <option value="custom">自定义降级链</option>
                <option value="disabled">禁用降级（只用自己的模型）</option>
              </select>
            </div>
            <div v-if="key.fallback_preference === 'custom'" class="fallback-chain-editor">
              <div class="chain-models">
                <div
                  v-for="(modelId, idx) in (key.custom_fallback_chain || [])"
                  :key="idx"
                  class="chain-model-item"
                >
                  <span class="chain-index">{{ idx + 1 }}</span>
                  <input
                    :value="modelId"
                    class="context-input"
                    placeholder="模型名称 (如 Qwen/Qwen3-8B)"
                    @change="updateCustomChainModel(key, idx, $event.target.value)"
                  />
                  <button class="action-btn delete-btn" @click="removeCustomChainModel(key, idx)">删除</button>
                </div>
                <button class="action-btn" style="margin-top: 4px;" @click="addCustomChainModel(key)">
                  + 添加模型
                </button>
              </div>
              <div class="context-config-add" style="margin-top: 8px;">
                <button class="action-btn save-btn" @click="saveFallbackPreference(key)">保存降级链</button>
              </div>
            </div>
            <div v-else-if="key.fallback_preference === 'disabled'" class="fallback-disabled-hint">
              降级已禁用。当模型调用失败时将直接报错，不会尝试其他模型。
            </div>
            <div v-else class="fallback-default-hint">
              使用管理员配置的默认降级链。
            </div>
          </div>
        </div>
      </div>
      
      <div v-else class="empty-state">
        <p>暂无其他供应商 Key</p>
      </div>
    </div>
    
    <!-- 安全提示 -->
    <div class="security-notice">
      <h4 class="notice-title">
        <svg class="notice-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
        安全说明
      </h4>
      <ul class="notice-list">
        <li>Key 使用 RSA 加密传输</li>
        <li>仅存储在 Redis 内存中，不落库</li>
        <li>到期自动清除，可随时手动删除</li>
        <li>前端不保存任何 Key，仅保存无意义 Token</li>
      </ul>
    </div>

    <!-- Token 使用统计 -->
    <div class="token-usage-section">
      <h3 class="subsection-title">Token 使用统计</h3>
      <div v-if="tokenUsage" class="token-usage-stats">
        <div class="stat-card">
          <div class="stat-label">今日使用</div>
          <div class="stat-value">{{ formatNumber(tokenUsage.today_tokens) }}</div>
          <div class="stat-unit">tokens</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">本月使用</div>
          <div class="stat-value">{{ formatNumber(tokenUsage.this_month_tokens) }}</div>
          <div class="stat-unit">tokens</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">总使用量</div>
          <div class="stat-value">{{ formatNumber(tokenUsage.total_tokens) }}</div>
          <div class="stat-unit">tokens</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">消息总数</div>
          <div class="stat-value">{{ formatNumber(tokenUsage.total_messages) }}</div>
          <div class="stat-unit">条</div>
        </div>
      </div>
      <div v-if="tokenUsage && Object.keys(tokenUsage.by_model).length > 0" class="model-usage">
        <h4 class="model-usage-title">按模型统计</h4>
        <div v-for="(tokens, model) in tokenUsage.by_model" :key="model" class="model-usage-item">
          <span class="model-name">{{ model }}</span>
          <span class="model-tokens">{{ formatNumber(tokens) }} tokens</span>
        </div>
      </div>
      <div v-if="!tokenUsage" class="loading-text">加载中...</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useApiKeyStore } from '@/stores/apikey'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/utils/api/index'

const store = useApiKeyStore()
const loading = ref(false)
const tokenUsage = ref(null)

// Forms
const siliconflowForm = reactive({ key: '', ttl: '24h', customHours: null })
const newKeyForm = reactive({ provider: '', key: '', remark: '', ttl: '24h', customHours: null })

// Context length config
const expandedContextConfig = ref(null)
const newContextLengths = reactive({})

// Fallback chain config
const expandedFallbackConfig = ref(null)

// TTL 选择变化处理
function onTTLChange(form) {
  if (form.ttl !== 'custom') {
    form.customHours = null
  }
}

// 获取实际 TTL 秒数
function getTTLSeconds(form) {
  if (form.ttl === 'custom' && form.customHours) {
    return form.customHours * 3600
  }
  const ttlMap = {
    '1h': 3600,
    '24h': 86400,
    '7d': 604800,
    '30d': 2592000,
    'never': 315360000,  // 10 年
  }
  return ttlMap[form.ttl] || 86400
}

onMounted(() => {
  store.loadFromStorage()
  store.listKeys().catch(() => {})
  loadTokenUsage()
})

async function loadTokenUsage() {
  try {
    const result = await api.getTokenUsage()
    tokenUsage.value = result
  } catch (error) {
    console.error('Failed to load token usage:', error)
  }
}

function formatNumber(num) {
  if (!num) return '0'
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

// Computed
const siliconflowKey = computed(() => store.siliconflowKey)
const otherKeys = computed(() => store.otherKeys)

// Methods
async function submitSiliconflowKey() {
  if (!siliconflowForm.key) {
    ElMessage.warning('请输入 API Key')
    return
  }
  
  loading.value = true
  try {
    const ttlSeconds = getTTLSeconds(siliconflowForm)
    await store.submitKey('siliconflow', siliconflowForm.key, ttlSeconds, '主 Key')
    ElMessage.success('硅基流动 Key 已保存')
    siliconflowForm.key = ''
    siliconflowForm.ttl = '24h'
    siliconflowForm.customHours = null
  } catch (e) {
    ElMessage.error('保存失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function submitNewKey() {
  if (!newKeyForm.provider || !newKeyForm.key) {
    ElMessage.warning('请选择供应商并输入 Key')
    return
  }
  
  loading.value = true
  try {
    const ttlSeconds = getTTLSeconds(newKeyForm)
    await store.submitKey(newKeyForm.provider, newKeyForm.key, ttlSeconds, newKeyForm.remark)
    ElMessage.success(`${getProviderName(newKeyForm.provider)} Key 已添加`)
    newKeyForm.provider = ''
    newKeyForm.key = ''
    newKeyForm.remark = ''
    newKeyForm.ttl = '24h'
    newKeyForm.customHours = null
  } catch (e) {
    ElMessage.error('添加失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function testKey(token) {
  try {
    ElMessage.info('正在测试连接...')
    const result = await store.testKey(token)
    if (result.success) {
      ElMessage.success('测试成功：' + result.message)
    } else {
      ElMessage.warning('测试失败：' + result.message)
    }
  } catch (e) {
    ElMessage.error('测试失败：' + (e.message || '未知错误'))
  }
}

async function deleteKey(token) {
  try {
    await ElMessageBox.confirm('确定要清除此 API Key 吗？此操作不可恢复。', '确认删除', {
      type: 'warning',
    })
    await store.deleteKey(token)
    ElMessage.success('Key 已清除')
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败：' + (e.message || '未知错误'))
    }
  }
}

async function toggleEnabled(key) {
  try {
    await store.toggleEnabled(key.token, !key.enabled)
    ElMessage.success(`Key 已${key.enabled ? '禁用' : '启用'}`)
  } catch (e) {
    ElMessage.error('操作失败：' + (e.message || '未知错误'))
  }
}

// Context length config functions
function toggleContextConfig(token) {
  if (expandedContextConfig.value === token) {
    expandedContextConfig.value = null
  } else {
    expandedContextConfig.value = token
    if (!newContextLengths[token]) {
      newContextLengths[token] = { model: '', value: null }
    }
  }
}

function addContextLength(key) {
  const token = key.token
  const input = newContextLengths[token]
  if (!input.model || !input.value) {
    ElMessage.warning('请输入模型名称和 context length')
    return
  }
  if (!key.context_lengths) {
    key.context_lengths = {}
  }
  key.context_lengths[input.model] = input.value
  newContextLengths[token] = { model: '', value: null }
}

function removeContextLength(key, model) {
  delete key.context_lengths[model]
}

async function saveContextLengths(key) {
  try {
    await store.updateContextLengths(key.token, key.context_lengths || {})
    ElMessage.success('模型上下文长度配置已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + (e.message || '未知错误'))
  }
}

// Fallback chain config functions
function toggleFallbackConfig(token) {
  if (expandedFallbackConfig.value === token) {
    expandedFallbackConfig.value = null
  } else {
    expandedFallbackConfig.value = token
    // 如果还没有加载过偏好，从后端获取
    const key = [...(store.tokens || [])].find(t => t.token === token)
    if (key && key.fallback_preference === undefined) {
      loadFallbackPreference(key)
    }
  }
}

async function loadFallbackPreference(key) {
  try {
    const res = await api.get(`/api/v1/agent/apikey/${key.token}/fallback-preference`)
    const data = await res.json()
    if (data) {
      key.fallback_preference = data.fallback_preference || 'use_admin_default'
      key.custom_fallback_chain = data.custom_fallback_chain || []
    }
  } catch (e) {
    console.error('加载降级链偏好失败:', e)
    key.fallback_preference = 'use_admin_default'
    key.custom_fallback_chain = []
  }
}

async function updateFallbackPreference(key, preference) {
  key.fallback_preference = preference
  if (preference !== 'custom') {
    key.custom_fallback_chain = []
  }
  // 立即保存非 custom 模式
  if (preference !== 'custom') {
    await saveFallbackPreference(key)
  }
}

function updateCustomChainModel(key, idx, value) {
  if (!key.custom_fallback_chain) {
    key.custom_fallback_chain = []
  }
  key.custom_fallback_chain[idx] = value
}

function addCustomChainModel(key) {
  if (!key.custom_fallback_chain) {
    key.custom_fallback_chain = []
  }
  key.custom_fallback_chain.push('')
}

function removeCustomChainModel(key, idx) {
  key.custom_fallback_chain.splice(idx, 1)
}

async function saveFallbackPreference(key) {
  try {
    await api.put(`/api/v1/agent/apikey/${key.token}/fallback-preference`, {
      fallback_preference: key.fallback_preference || 'use_admin_default',
      custom_fallback_chain: key.fallback_preference === 'custom' ? (key.custom_fallback_chain || []) : [],
    })
    ElMessage.success('降级链配置已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + (e.message || '未知错误'))
  }
}

// Helpers
function getStatusText(status) {
  const map = {
    unverified: '未验证',
    verified: '已验证',
    invalid: '已失效',
    expired: '已过期',
  }
  return map[status] || '未知'
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

function getRemainingTime(key) {
  if (!key || !key.expires_at) return '未知'
  const expiresAt = new Date(key.expires_at)
  const now = new Date()
  const diff = expiresAt - now
  
  if (diff <= 0) return '已过期'
  
  const hours = Math.floor(diff / (1000 * 60 * 60))
  const days = Math.floor(hours / 24)
  
  if (days > 0) return `${days} 天`
  return `${hours} 小时`
}
</script>

<style scoped>
.api-key-manager {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.section-title {
  font-size: 20px;
  margin-bottom: 20px;
}

.key-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
  background: var(--bg-primary);
}

.required-key {
  border-color: var(--primary);
  background: var(--color-primary-50);
}

.key-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.provider-icon-svg {
  width: 20px;
  height: 20px;
  color: var(--text-secondary);
}

.notice-icon {
  width: 16px;
  height: 16;
  margin-right: 4px;
}

.provider-name {
  font-weight: 600;
  flex: 1;
}

.required-badge {
  background: var(--warning);
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.status-badge.verified {
  background: var(--success);
  color: white;
}

.status-badge.unverified {
  background: var(--text-tertiary);
  color: white;
}

.status-badge.invalid {
  background: var(--danger);
  color: white;
}

.status-badge.expired {
  background: var(--text-tertiary);
  color: white;
}

.key-card-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.key-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.key-remark {
  color: var(--text-secondary);
}

.key-expiry {
  color: var(--text-tertiary);
  font-size: 14px;
}

.key-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}

.test-btn {
  background: var(--color-success-50, #e1f3d8);
  color: var(--success);
}
.test-btn:hover {
  background: var(--color-success-100, #c6f0b3);
}

.toggle-btn {
  background: var(--color-primary-100);
  color: var(--primary);
}
.toggle-btn:hover {
  background: var(--color-primary-100);
}

.delete-btn {
  background: var(--color-danger-100, #fde2e2);
  color: var(--danger);
}
.delete-btn:hover {
  background: var(--color-danger-100, #fbc4c4);
}

.guide-text {
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.guide-link {
  color: var(--primary);
  text-decoration: none;
}

.add-key-form,
.add-key-form-expanded {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.key-input,
.remark-input,
.provider-select,
.ttl-select,
.custom-ttl-input {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 14px;
}

.custom-ttl-input {
  width: 100px;
}

.key-input {
  flex: 1;
  min-width: 200px;
}

.remark-input {
  width: 120px;
}

.provider-select,
.ttl-select {
  width: 140px;
}

.submit-btn {
  padding: 8px 20px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.submit-btn:disabled {
  background: var(--primary-hover);
  cursor: not-allowed;
}

.other-keys-section {
  margin-top: 24px;
}

.subsection-title {
  font-size: 16px;
  margin-bottom: 16px;
  color: var(--text-secondary);
}

.key-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: var(--text-tertiary);
  background: var(--bg-secondary);
  border-radius: 8px;
}

.security-notice {
  margin-top: 32px;
  padding: 16px;
  background: var(--color-primary-50);
  border: 1px solid var(--color-primary-100);
  border-radius: 8px;
}

.notice-title {
  font-size: 14px;
  margin-bottom: 8px;
  color: var(--primary);
}

.notice-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.notice-list li {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 4px 0;
}

.notice-list li::before {
  content: '✓ ';
  color: var(--success);
}

.token-usage-section {
  margin-top: 32px;
  padding: 20px;
  background: var(--bg-secondary);
  border-radius: 8px;
}

.token-usage-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.stat-card {
  background: var(--bg-primary);
  padding: 16px;
  border-radius: 8px;
  text-align: center;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.stat-label {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-unit {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.model-usage {
  margin-top: 20px;
}

.model-usage-title {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.model-usage-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-primary);
  border-radius: 4px;
  margin-bottom: 8px;
}

.model-name {
  font-size: 13px;
  color: var(--text-primary);
}

.model-tokens {
  font-size: 13px;
  color: var(--primary);
  font-weight: 500;
}

.loading-text {
  text-align: center;
  color: var(--text-tertiary);
  padding: 20px;
}

/* Context length config */
.context-config-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.context-config-header {
  margin-bottom: 12px;
}

.context-config-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  display: block;
  margin-bottom: 4px;
}

.context-config-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

.context-config-list {
  margin-bottom: 12px;
}

.context-config-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
  margin-bottom: 8px;
}

.context-config-item .model-name {
  flex: 1;
  font-size: 13px;
  font-family: monospace;
}

.context-input {
  padding: 4px 8px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 13px;
  width: 120px;
}

.context-input.model-input {
  width: 200px;
}

.context-unit {
  font-size: 12px;
  color: var(--text-tertiary);
}

.empty-context {
  font-size: 13px;
  color: var(--text-tertiary);
  padding: 12px;
  text-align: center;
  background: var(--bg-secondary);
  border-radius: 4px;
}

.context-config-add {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.action-btn.config-btn {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.action-btn.save-btn {
  background: var(--success);
  color: white;
  border-color: var(--success);
}

.fallback-preference-select {
  margin-bottom: 12px;
}

.fallback-preference-select .model-select {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 13px;
  background: var(--bg-primary);
  cursor: pointer;
}

.fallback-chain-editor {
  margin-top: 8px;
}

.fallback-chain-editor .chain-models {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fallback-chain-editor .chain-model-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fallback-chain-editor .chain-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.fallback-chain-editor .context-input {
  flex: 1;
  width: auto;
}

.fallback-disabled-hint,
.fallback-default-hint {
  font-size: 13px;
  color: var(--text-tertiary);
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: 4px;
  margin-top: 8px;
}

.fallback-disabled-hint {
  color: var(--warning);
  background: #fff7e6;
}
</style>
