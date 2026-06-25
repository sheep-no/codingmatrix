<template>
  <div class="admin-model-manager">
    <h3 class="section-title">系统模型管理</h3>
    <p class="section-desc">管理系统默认免费模型。切换后影响所有用户的默认模型选择。</p>

    <!-- 当前默认模型 -->
    <div class="current-default">
      <div class="default-label">当前默认模型</div>
      <div class="default-value">
        <span class="model-name">{{ currentDefault.name || currentDefault.id || '-' }}</span>
        <span class="model-desc">{{ currentDefault.description }}</span>
      </div>
    </div>

    <!-- 模型健康状态概览 -->
    <div class="health-overview">
      <h3 class="subsection-title">模型健康状态</h3>
      <div class="health-grid">
        <div v-for="model in modelsWithHealth" :key="model.id" :class="['health-card', getHealthStatus(model)]">
          <div class="health-card-header">
            <span class="health-model-name">{{ model.name }}</span>
            <span :class="['health-badge', getHealthStatus(model)]">
              {{ getHealthStatusText(model) }}
            </span>
          </div>
          <div class="health-metrics">
            <div class="metric">
              <span class="metric-label">成功率</span>
              <span class="metric-value">{{ formatPercent(model.health_score) }}%</span>
            </div>
            <div class="metric">
              <span class="metric-label">延迟</span>
              <span class="metric-value">{{ formatLatency(model.avg_latency) }}ms</span>
            </div>
            <div class="metric">
              <span class="metric-label">调用次数</span>
              <span class="metric-value">{{ model.total_calls || 0 }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 模型搜索 -->
    <div class="filter-bar">
      <input
        v-model="modelSearch"
        type="text"
        placeholder="搜索模型名称、ID 或描述..."
        class="search-input"
      />
      <span class="filter-count">{{ filteredModels.length }} / {{ models.length }}</span>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <span class="loading-spinner"></span> 加载中...
    </div>

    <!-- 空状态 -->
    <div v-else-if="!models.length" class="empty-state">
      暂无可用模型
    </div>

    <!-- 模型列表 -->
    <div v-else class="model-grid">
      <div
        v-for="model in filteredModels"
        :key="model.id"
        :class="['model-card', { active: model.is_default }]"
        @click="confirmSwitchDefault(model)"
      >
        <div class="model-card-header">
          <span class="model-card-name">{{ model.name }}</span>
          <span v-if="model.is_default" class="default-badge">默认</span>
        </div>
        <div class="model-card-id">{{ model.id }}</div>
        <div class="model-card-desc">{{ model.description }}</div>
        <div class="model-card-caps">
          <span v-for="cap in model.capabilities" :key="cap" class="cap-tag">{{ cap }}</span>
        </div>
        <div class="model-card-tags">
          <span v-for="tag in model.tags" :key="tag" class="tag-chip">{{ tag }}</span>
        </div>
        <div v-if="model.health_score !== undefined" class="model-card-health">
          <div :class="['health-indicator', getHealthClass(model.health_score)]">
            {{ model.health_score }}%
          </div>
        </div>
      </div>
    </div>

    <!-- 上下文长度管理 -->
    <div class="context-section">
      <h3 class="section-title">模型上下文窗口配置</h3>
      <p class="section-desc">配置每个模型的最大上下文长度（token）。配置文件优先于内置默认值。</p>

      <!-- 搜索 -->
      <div class="filter-bar">
        <input
          v-model="contextSearch"
          type="text"
          placeholder="搜索模型 Key..."
          class="search-input"
        />
        <button class="sort-btn" @click="toggleSort">
          {{ sortOrder === 'asc' ? '↑ A-Z' : '↓ Z-A' }}
        </button>
      </div>

      <div v-if="loadingContext" class="loading-state">
        <span class="loading-spinner"></span> 加载中...
      </div>

      <div v-else-if="!sortedFilteredContextKeys.length" class="empty-state">
        暂无上下文长度配置
      </div>

      <div v-else class="context-table-wrap">
        <table class="context-table">
          <thead>
            <tr>
              <th>模型 Key</th>
              <th>上下文长度 (token)</th>
              <th>来源</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="key in sortedFilteredContextKeys" :key="key">
              <td class="ctx-key">{{ key }}</td>
              <td>
                <input
                  v-if="contextLengths[key]._editing"
                  v-model.number="contextLengths[key]._editValue"
                  type="number"
                  min="1"
                  class="ctx-input"
                  @keyup.enter="saveContextLength(key)"
                  @keyup.escape="cancelEdit(key)"
                />
                <span v-else class="ctx-value">{{ formatTokens(contextLengths[key].context_length) }}</span>
              </td>
              <td>
                <span :class="['source-tag', contextLengths[key].source]">
                  {{ contextLengths[key].source === 'config' ? '自定义' : '内置' }}
                </span>
              </td>
              <td class="ctx-actions">
                <template v-if="contextLengths[key]._editing">
                  <button class="action-btn save" @click="saveContextLength(key)">保存</button>
                  <button class="action-btn cancel" @click="cancelEdit(key)">取消</button>
                </template>
                <template v-else>
                  <button class="action-btn edit" @click="startEdit(key)">编辑</button>
                  <button
                    v-if="contextLengths[key].source === 'config'"
                    class="action-btn delete"
                    @click="deleteContextLength(key)"
                  >恢复默认</button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 添加新模型上下文 -->
      <div class="add-context">
        <input
          v-model="newModelKey"
          type="text"
          placeholder="模型 Key (如 Qwen/Qwen3-8B)"
          class="ctx-input add-input"
        />
        <input
          v-model.number="newContextLength"
          type="number"
          min="1"
          placeholder="上下文长度"
          class="ctx-input add-input"
        />
        <button class="action-btn edit" @click="addContextLength">添加</button>
      </div>
    </div>

    <!-- 刷新按钮 -->
    <div class="actions">
      <button class="reload-btn" :disabled="loading || loadingContext" @click="loadAll">
        <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
        {{ loading || loadingContext ? '加载中...' : '刷新' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '@/utils/api/index'
import { ElMessage, ElMessageBox } from 'element-plus'

const models = ref([])
const contextLengths = ref({})
const newModelKey = ref('')
const newContextLength = ref(null)
const modelSearch = ref('')
const contextSearch = ref('')
const sortOrder = ref('asc')
const loading = ref(false)
const loadingContext = ref(false)
const modelHealthData = ref({})

const currentDefault = computed(() => {
  return models.value.find(m => m.is_default) || {}
})

const modelsWithHealth = computed(() => {
  return models.value.map(m => ({
    ...m,
    health_score: modelHealthData.value[m.id]?.health_score,
    avg_latency: modelHealthData.value[m.id]?.avg_latency_ms,
    total_calls: modelHealthData.value[m.id]?.total_requests
  }))
})

const filteredModels = computed(() => {
  const q = modelSearch.value.toLowerCase().trim()
  if (!q) return models.value
  return models.value.filter(m =>
    m.name?.toLowerCase().includes(q) ||
    m.id?.toLowerCase().includes(q) ||
    m.description?.toLowerCase().includes(q) ||
    m.model_key?.toLowerCase().includes(q)
  )
})

const sortedFilteredContextKeys = computed(() => {
  const q = contextSearch.value.toLowerCase().trim()
  let keys = Object.keys(contextLengths.value)
  if (q) {
    keys = keys.filter(k => k.toLowerCase().includes(q))
  }
  keys.sort((a, b) => sortOrder.value === 'asc' ? a.localeCompare(b) : b.localeCompare(a))
  return keys
})

function toggleSort() {
  sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'
}

async function loadModels() {
  loading.value = true
  try {
    const resp = await api.get('/api/v1/models/')
    if (!resp.ok) return
    const data = await resp.json()
    models.value = data.models || []
  } catch {
    ElMessage.error('加载模型列表失败')
  } finally {
    loading.value = false
  }
}

async function loadContextLengths() {
  loadingContext.value = true
  try {
    const resp = await api.get('/api/v2/models/context-lengths')
    if (!resp.ok) return
    const data = await resp.json()
    if (data.success && data.models) {
      const result = {}
      for (const [key, val] of Object.entries(data.models)) {
        result[key] = { ...val, _editing: false, _editValue: val.context_length }
      }
      contextLengths.value = result
    }
  } catch {
    ElMessage.error('加载上下文长度失败')
  } finally {
    loadingContext.value = false
  }
}

async function loadModelHealth() {
  try {
    const resp = await api.get('/api/v1/models/health')
    if (resp.ok) {
      const data = await resp.json()
      modelHealthData.value = data.models || {}
    }
  } catch {
    // 健康数据加载失败不影响主功能
  }
}

function loadAll() {
  loadModels()
  loadContextLengths()
  loadModelHealth()
}

async function confirmSwitchDefault(model) {
  if (model.is_default) return
  try {
    await ElMessageBox.confirm(
      `确定将默认模型切换为「${model.name}」？此操作影响所有用户。`,
      '切换默认模型',
      { confirmButtonText: '确定切换', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }

  try {
    const resp = await api.post('/api/v2/models/default', { model_id: model.id })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      ElMessage.error('切换失败: ' + (err.detail || resp.statusText))
      return
    }
    const data = await resp.json()
    if (data.success) {
      models.value.forEach(m => { m.is_default = m.id === model.id })
      ElMessage.success(`默认模型已切换为 ${data.new_default}`)
    }
  } catch (e) {
    ElMessage.error('切换失败: ' + e.message)
  }
}

function formatTokens(val) {
  if (!val) return '-'
  if (val >= 1024 * 1024) return `${(val / 1024 / 1024).toFixed(0)}M`
  if (val >= 1024) return `${(val / 1024).toFixed(0)}k`
  return String(val)
}

function formatPercent(val) {
  if (val === undefined || val === null) return '-'
  return Math.round(val)
}

function formatLatency(val) {
  if (val === undefined || val === null) return '-'
  return Math.round(val)
}

function getHealthStatus(model) {
  if (model.health_score === undefined) return 'unknown'
  if (model.health_score >= 80) return 'healthy'
  if (model.health_score >= 50) return 'degraded'
  return 'critical'
}

function getHealthStatusText(model) {
  const status = getHealthStatus(model)
  const texts = {
    healthy: '健康',
    degraded: '降级',
    critical: '熔断',
    unknown: '未知'
  }
  return texts[status] || '未知'
}

function getHealthClass(score) {
  if (score === undefined) return 'unknown'
  if (score >= 80) return 'good'
  if (score >= 50) return 'warning'
  return 'critical'
}

function startEdit(key) {
  const item = contextLengths.value[key]
  item._editValue = item.context_length
  item._editing = true
}

function cancelEdit(key) {
  const item = contextLengths.value[key]
  item._editValue = item.context_length
  item._editing = false
}

async function saveContextLength(key) {
  const item = contextLengths.value[key]
  if (!item._editValue || item._editValue < 1) {
    ElMessage.warning('上下文长度必须大于 0')
    return
  }
  try {
    const resp = await api.put('/api/v2/models/context-length', {
      model_key: key,
      context_length: item._editValue,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      ElMessage.error('保存失败: ' + (err.detail || resp.statusText))
      return
    }
    const data = await resp.json()
    if (data.success) {
      item.context_length = item._editValue
      item.source = 'config'
      item._editing = false
      ElMessage.success(`已更新 ${key} 上下文长度`)
    }
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  }
}

async function deleteContextLength(key) {
  try {
    const resp = await api.delete(`/api/v2/models/context-length/${key}`)
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      ElMessage.error('删除失败: ' + (err.detail || resp.statusText))
      return
    }
    const data = await resp.json()
    if (data.success) {
      delete contextLengths.value[key]
      ElMessage.success(data.message)
    }
  } catch (e) {
    ElMessage.error('删除失败: ' + e.message)
  }
}

async function addContextLength() {
  if (!newModelKey.value || !newContextLength.value) {
    ElMessage.warning('请填写模型 Key 和上下文长度')
    return
  }
  try {
    const resp = await api.put('/api/v2/models/context-length', {
      model_key: newModelKey.value,
      context_length: newContextLength.value,
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      ElMessage.error('添加失败: ' + (err.detail || resp.statusText))
      return
    }
    const data = await resp.json()
    if (data.success) {
      contextLengths.value[newModelKey.value] = {
        context_length: newContextLength.value,
        source: 'config',
        _editing: false,
        _editValue: newContextLength.value,
      }
      newModelKey.value = ''
      newContextLength.value = null
      ElMessage.success('添加成功')
    }
  } catch (e) {
    ElMessage.error('添加失败: ' + e.message)
  }
}

onMounted(loadAll)
</script>

<style scoped>
.admin-model-manager { padding: 20px; max-width: 1000px; margin: 0 auto; }
.section-title { font-size: 18px; margin-bottom: 8px; color: var(--text-primary); }
.subsection-title { font-size: 16px; margin-bottom: 12px; color: var(--text-primary); }
.section-desc { font-size: 14px; color: var(--text-tertiary); margin-bottom: 24px; }

.current-default {
  display: flex; align-items: center; gap: 16px;
  padding: 16px 20px;
  background: var(--primary-50, rgba(13, 148, 136, 0.08));
  border: 1px solid var(--primary-200, rgba(13, 148, 136, 0.2));
  border-radius: 8px; margin-bottom: 24px;
}
.default-label { font-size: 14px; color: var(--primary); font-weight: 600; white-space: nowrap; }
.default-value { display: flex; flex-direction: column; }
.model-name { font-size: 16px; font-weight: 600; color: var(--text-primary); }
.model-desc { font-size: 13px; color: var(--text-tertiary); }

/* 健康状态概览 */
.health-overview {
  margin-bottom: 24px;
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
}

.health-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.health-card {
  padding: 12px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
}

.health-card.healthy {
  border-color: var(--success);
}

.health-card.degraded {
  border-color: var(--warning);
}

.health-card.critical {
  border-color: var(--danger);
}

.health-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.health-model-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.health-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.health-badge.healthy {
  background: var(--success-bg);
  color: var(--success);
}

.health-badge.degraded {
  background: var(--warning-bg);
  color: var(--warning);
}

.health-badge.critical {
  background: var(--danger-bg);
  color: var(--danger);
}

.health-badge.unknown {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.health-metrics {
  display: flex;
  gap: 12px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.metric-label {
  font-size: 11px;
  color: var(--text-tertiary);
}

.metric-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.filter-bar {
  display: flex; align-items: center; gap: 12px; margin-bottom: 16px;
}
.search-input {
  flex: 1; padding: 8px 12px;
  border: 1px solid var(--border-color); border-radius: 6px;
  font-size: 13px; background: var(--bg-primary); color: var(--text-primary);
}
.search-input:focus { outline: none; border-color: var(--primary); }
.filter-count { font-size: 12px; color: var(--text-tertiary); white-space: nowrap; }
.sort-btn {
  padding: 6px 12px; border: 1px solid var(--border-color); border-radius: 4px;
  font-size: 12px; cursor: pointer; background: var(--bg-secondary); color: var(--text-secondary);
  white-space: nowrap;
}
.sort-btn:hover { border-color: var(--primary); color: var(--primary); }

.loading-state {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 32px; color: var(--text-tertiary); font-size: 14px;
}
.loading-spinner {
  width: 16px; height: 16px; border: 2px solid var(--border-color);
  border-top-color: var(--primary); border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.empty-state {
  text-align: center; padding: 32px; color: var(--text-tertiary); font-size: 14px;
}

.model-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px; margin-bottom: 32px;
}
.model-card {
  border: 1px solid var(--border-color); border-radius: 8px; padding: 16px;
  cursor: pointer; transition: all 0.2s; background: var(--bg-secondary);
}
.model-card:hover { border-color: var(--primary); box-shadow: 0 2px 8px var(--shadow-color); }
.model-card.active { border-color: var(--primary); background: var(--primary-50); }

.model-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.model-card-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.default-badge {
  padding: 2px 8px; background: var(--primary); color: white;
  border-radius: 4px; font-size: 11px; font-weight: 600;
}
.model-card-id { font-size: 12px; color: var(--text-tertiary); margin-bottom: 8px; font-family: monospace; }
.model-card-desc { font-size: 13px; color: var(--text-secondary); margin-bottom: 12px; }
.model-card-caps { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.cap-tag {
  padding: 2px 8px;
  background: var(--success-bg, rgba(16, 185, 129, 0.1));
  color: var(--success);
  border-radius: 4px; font-size: 11px;
}
.model-card-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.tag-chip {
  padding: 2px 8px;
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  border-radius: 4px; font-size: 11px;
}

.model-card-health {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-color);
}

.health-indicator {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}

.health-indicator.good {
  background: var(--success-bg);
  color: var(--success);
}

.health-indicator.warning {
  background: var(--warning-bg);
  color: var(--warning);
}

.health-indicator.critical {
  background: var(--danger-bg);
  color: var(--danger);
}

.health-indicator.unknown {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

/* 上下文长度表格 */
.context-section { margin-bottom: 32px; }
.context-table-wrap { overflow-x: auto; margin-bottom: 16px; }
.context-table {
  width: 100%; border-collapse: collapse;
  font-size: 13px; color: var(--text-primary);
}
.context-table th {
  text-align: left; padding: 10px 12px;
  border-bottom: 2px solid var(--border-color);
  color: var(--text-secondary); font-weight: 600; font-size: 12px;
}
.context-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
  vertical-align: middle;
}
.context-table tr:hover { background: var(--bg-tertiary); }
.ctx-key { font-family: monospace; font-size: 12px; max-width: 280px; word-break: break-all; }
.ctx-value { font-family: monospace; font-weight: 600; }

.source-tag {
  display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px;
}
.source-tag.config {
  background: var(--warning-bg);
  color: var(--warning);
}
.source-tag.builtin {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.ctx-input {
  padding: 4px 8px; border: 1px solid var(--border-color);
  border-radius: 4px; font-size: 13px; font-family: monospace;
  background: var(--bg-primary); color: var(--text-primary);
  width: 120px;
}
.ctx-input:focus { outline: none; border-color: var(--primary); }

.ctx-actions { display: flex; gap: 6px; }
.action-btn {
  padding: 4px 10px; border: 1px solid var(--border-color);
  border-radius: 4px; font-size: 12px; cursor: pointer;
  background: var(--bg-secondary); color: var(--text-secondary);
  transition: all 0.15s;
}
.action-btn:hover { border-color: var(--primary); color: var(--primary); }
.action-btn.save { background: var(--primary); color: var(--bg-primary); border-color: var(--primary); }
.action-btn.save:hover { background: var(--primary-hover); }
.action-btn.delete { color: var(--danger); border-color: var(--danger); }
.action-btn.delete:hover { background: var(--danger); color: var(--bg-primary); }

.add-context {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}
.add-input { width: 200px; }

.actions { text-align: center; }
.reload-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 20px; background: var(--primary); color: var(--bg-primary);
  border: none; border-radius: 6px; cursor: pointer; font-size: 14px;
  font-weight: 500; transition: background 0.2s;
}
.reload-btn:hover:not(:disabled) { background: var(--primary-hover); }
.reload-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-icon { width: 16px; height: 16px; }
</style>
