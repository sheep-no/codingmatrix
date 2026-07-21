<template>
  <div class="unified-model-config">
    <h3 class="section-title">模型配置</h3>
    <p class="section-desc">管理所有 AI 模型，支持一键添加、启用/禁用、配置参数</p>

    <!-- 快速添加模型 -->
    <div class="quick-add">
      <h4 class="subsection-title">快速添加模型</h4>
      <div class="add-form">
        <div class="form-row">
          <div class="form-group">
            <label>模型 ID</label>
            <input v-model="newModel.id" type="text" placeholder="如: gpt-4o" class="form-input" />
          </div>
          <div class="form-group">
            <label>API 名称</label>
            <input v-model="newModel.name" type="text" placeholder="如: gpt-4o" class="form-input" />
          </div>
          <div class="form-group">
            <label>显示名称</label>
            <input v-model="newModel.display_name" type="text" placeholder="如: GPT-4o" class="form-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>供应商</label>
            <select v-model="newModel.provider" class="form-select">
              <option v-for="p in providers" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>类型</label>
            <select v-model="newModel.model_type" class="form-select">
              <option value="chat">对话</option>
              <option value="embedding">嵌入</option>
              <option value="vision">视觉</option>
              <option value="image">图像</option>
              <option value="audio">音频</option>
            </select>
          </div>
          <div class="form-group">
            <label>上下文长度</label>
            <input v-model.number="newModel.context_length" type="number" class="form-input" />
          </div>
          <div class="form-group">
            <label>&nbsp;</label>
            <button :disabled="adding" class="add-btn" @click="addModel">
              {{ adding ? '添加中...' : '添加模型' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 模型列表 -->
    <div class="model-list">
      <div class="list-header">
        <h4 class="subsection-title">已配置模型 ({{ models.length }})</h4>
        <div class="filter-bar">
          <input v-model="searchQuery" type="text" placeholder="搜索模型..." class="search-input" />
          <select v-model="filterType" class="filter-select">
            <option value="">全部类型</option>
            <option value="chat">对话</option>
            <option value="embedding">嵌入</option>
            <option value="vision">视觉</option>
            <option value="image">图像</option>
            <option value="audio">音频</option>
          </select>
        </div>
      </div>

      <div class="model-grid">
        <div
          v-for="model in filteredModels"
          :key="model.id"
          :class="['model-card', { disabled: !model.enabled }]"
        >
          <div class="card-header">
            <div class="model-info">
              <span class="model-name">{{ model.display_name }}</span>
              <span class="model-id">{{ model.id }}</span>
            </div>
            <div class="card-actions">
              <button
                :class="['toggle-btn', { active: model.enabled }]"
                @click="toggleModel(model.id)"
              >
                {{ model.enabled ? '禁用' : '启用' }}
              </button>
              <button class="delete-btn" @click="deleteModel(model.id)">删除</button>
            </div>
          </div>

          <div class="model-meta">
            <span :class="['type-badge', model.type]">{{ typeLabels[model.type] || model.type }}</span>
            <span v-if="model.is_reasoning" class="reasoning-badge">推理</span>
            <span class="context-badge">{{ formatContext(model.context_length) }}</span>
          </div>

          <div class="model-details">
            <div class="detail-item">
              <span class="label">API:</span>
              <span class="value">{{ model.name }}</span>
            </div>
            <div class="detail-item">
              <span class="label">温度:</span>
              <span class="value">{{ model.temperature }}</span>
            </div>
            <div class="detail-item">
              <span class="label">超时:</span>
              <span class="value">{{ model.timeout }}s</span>
            </div>
          </div>

          <div v-if="model.tags && model.tags.length" class="model-tags">
            <span v-for="tag in model.tags" :key="tag" class="tag">{{ tag }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Agent 角色配置 -->
    <div class="agent-config">
      <h4 class="subsection-title">Agent 角色配置</h4>
      <p class="section-desc">配置各角色使用的模型</p>

      <div class="roles-grid">
        <div v-for="(modelId, role) in agentRoles" :key="role" class="role-card">
          <div class="role-header">
            <span :class="['role-badge', role]">{{ roleLabels[role] || role }}</span>
          </div>
          <select
            :value="modelId"
            class="role-select"
            @change="updateRole(role, $event.target.value)"
          >
            <option v-for="m in chatModels" :key="m.id" :value="m.id">
              {{ m.display_name }}
            </option>
          </select>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '@/utils/api/index'
import { ElMessage, ElMessageBox } from 'element-plus'

const models = ref([])
const providers = ref([])
const agentRoles = ref({})
const searchQuery = ref('')
const filterType = ref('')
const adding = ref(false)

const newModel = ref({
  id: '',
  name: '',
  display_name: '',
  provider: 'siliconflow',
  model_type: 'chat',
  context_length: 32768
})

const typeLabels = {
  chat: '对话',
  embedding: '嵌入',
  vision: '视觉',
  image: '图像',
  audio: '音频'
}

const roleLabels = {
  architect: '架构师',
  frontend: '前端',
  backend: '后端',
  reviewer: '审查员',
  fallback: '兜底'
}

const chatModels = computed(() => {
  return models.value.filter(m => m.type === 'chat' && m.enabled)
})

const filteredModels = computed(() => {
  let result = [...models.value]
  
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(m =>
      m.display_name?.toLowerCase().includes(q) ||
      m.id?.toLowerCase().includes(q) ||
      m.name?.toLowerCase().includes(q)
    )
  }
  
  if (filterType.value) {
    result = result.filter(m => m.type === filterType.value)
  }
  
  return result
})

function formatContext(tokens) {
  if (!tokens) return '-'
  if (tokens >= 1024 * 1024) return `${(tokens / 1024 / 1024).toFixed(0)}M`
  if (tokens >= 1024) return `${(tokens / 1024).toFixed(0)}k`
  return `${tokens}`
}

async function loadModels() {
  try {
    const resp = await api.get('/api/v2/model-config/models')
    if (resp.ok) {
      const data = await resp.json()
      models.value = data.models || []
    }
  } catch {
    ElMessage.error('加载模型列表失败')
  }
}

async function loadProviders() {
  try {
    const resp = await api.get('/api/v2/model-config/providers')
    if (resp.ok) {
      const data = await resp.json()
      providers.value = data.providers || []
    }
  } catch {
    // 忽略
  }
}

async function loadAgentConfig() {
  try {
    const resp = await api.get('/api/v2/model-config/agent')
    if (resp.ok) {
      const data = await resp.json()
      agentRoles.value = data.roles || {}
    }
  } catch {
    // 忽略
  }
}

async function addModel() {
  if (!newModel.value.id || !newModel.value.name || !newModel.value.display_name) {
    ElMessage.warning('请填写模型 ID、API 名称和显示名称')
    return
  }
  
  adding.value = true
  try {
    const resp = await api.post('/api/v2/model-config/models', newModel.value)
    if (resp.ok) {
      ElMessage.success('模型已添加')
      newModel.value = { id: '', name: '', display_name: '', provider: 'siliconflow', model_type: 'chat', context_length: 32768 }
      await loadModels()
    } else {
      const err = await resp.json().catch(() => ({}))
      ElMessage.error(err.detail || '添加失败')
    }
  } catch (e) {
    ElMessage.error('添加失败: ' + e.message)
  } finally {
    adding.value = false
  }
}

async function toggleModel(modelId) {
  try {
    const resp = await api.put(`/api/v2/model-config/models/${modelId}/toggle`)
    if (resp.ok) {
      const data = await resp.json()
      const model = models.value.find(m => m.id === modelId)
      if (model && data.enabled !== undefined) {
        model.enabled = data.enabled
      }
      ElMessage.success('状态已切换')
    }
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function deleteModel(modelId) {
  try {
    await ElMessageBox.confirm('确定删除此模型？', '确认删除', { type: 'warning' })
  } catch {
    return
  }
  
  try {
    const resp = await api.delete(`/api/v2/model-config/models/${modelId}`)
    if (resp.ok) {
      models.value = models.value.filter(m => m.id !== modelId)
      ElMessage.success('模型已删除')
    }
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function updateRole(role, modelId) {
  try {
    const resp = await api.put('/api/v2/model-config/agent/role', { role, model_id: modelId })
    if (resp.ok) {
      agentRoles.value[role] = modelId
      ElMessage.success(`${roleLabels[role] || role} 已更新为 ${modelId}`)
    }
  } catch (e) {
    ElMessage.error('更新失败')
  }
}

onMounted(() => {
  loadModels()
  loadProviders()
  loadAgentConfig()
})
</script>

<style scoped>
.unified-model-config {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.section-desc {
  font-size: 14px;
  color: var(--text-tertiary);
  margin-bottom: 24px;
}

.subsection-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text-primary);
}

/* 快速添加 */
.quick-add {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;
}

.add-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.form-group {
  flex: 1;
  min-width: 150px;
}

.form-group label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.form-input,
.form-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--primary);
}

.add-btn {
  padding: 8px 20px;
  background: var(--primary);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
}

.add-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.add-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 模型列表 */
.model-list {
  margin-bottom: 24px;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.filter-bar {
  display: flex;
  gap: 8px;
}

.search-input,
.filter-select {
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.search-input {
  width: 200px;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.model-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 16px;
  background: var(--bg-primary);
  transition: all 0.2s;
}

.model-card:hover {
  border-color: var(--primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.model-card.disabled {
  opacity: 0.6;
  background: var(--bg-secondary);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.model-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.model-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.model-id {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: monospace;
}

.card-actions {
  display: flex;
  gap: 6px;
}

.toggle-btn {
  padding: 4px 10px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  background: var(--bg-secondary);
  color: var(--text-secondary);
}

.toggle-btn.active {
  background: var(--success-bg);
  color: var(--success);
  border-color: var(--success);
}

.delete-btn {
  padding: 4px 10px;
  border: 1px solid var(--danger);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  background: transparent;
  color: var(--danger);
}

.delete-btn:hover {
  background: var(--danger);
  color: white;
}

.model-meta {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.type-badge,
.reasoning-badge,
.context-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.type-badge {
  background: var(--primary-50);
  color: var(--primary);
}

.type-badge.embedding {
  background: var(--success-bg);
  color: var(--success);
}

.type-badge.vision,
.type-badge.image {
  background: var(--warning-bg);
  color: var(--warning);
}

.type-badge.audio {
  background: var(--danger-bg);
  color: var(--danger);
}

.reasoning-badge {
  background: var(--color-primary-50);
  color: var(--color-primary-700);
}

.context-badge {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.model-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.detail-item {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.detail-item .label {
  color: var(--text-tertiary);
  min-width: 40px;
}

.detail-item .value {
  color: var(--text-secondary);
  font-family: monospace;
}

.model-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.tag {
  padding: 2px 6px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  font-size: 11px;
  color: var(--text-tertiary);
}

/* Agent 配置 */
.agent-config {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 20px;
}

.roles-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.role-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.role-header {
  display: flex;
  align-items: center;
}

.role-badge {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.role-badge.architect {
  background: var(--primary-50);
  color: var(--primary);
}

.role-badge.frontend {
  background: var(--success-bg);
  color: var(--success);
}

.role-badge.backend {
  background: var(--warning-bg);
  color: var(--warning);
}

.role-badge.reviewer {
  background: var(--danger-bg);
  color: var(--danger);
}

.role-badge.fallback {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.role-select {
  padding: 6px 8px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.role-select:focus {
  outline: none;
  border-color: var(--primary);
}
</style>
