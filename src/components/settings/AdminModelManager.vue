<template>
  <div class="admin-model-manager">
    <h3 class="section-title">系统模型管理</h3>
    <p class="section-desc">管理系统默认免费模型。切换后影响所有用户的默认模型选择。</p>

    <!-- 当前默认模型 -->
    <div class="current-default">
      <div class="default-label">当前默认模型</div>
      <div class="default-value">
        <span class="model-name">{{ currentDefault.name || currentDefault.id }}</span>
        <span class="model-desc">{{ currentDefault.description }}</span>
      </div>
    </div>

    <!-- 模型列表 -->
    <div class="model-grid">
      <div
        v-for="model in models"
        :key="model.id"
        :class="['model-card', { active: model.is_default }]"
        @click="switchDefault(model.id)"
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
      </div>
    </div>

    <!-- 上下文长度管理 -->
    <div class="context-section">
      <h3 class="section-title">模型上下文窗口配置</h3>
      <p class="section-desc">配置每个模型的最大上下文长度（token）。配置文件优先于内置默认值。</p>

      <div class="context-table-wrap">
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
            <tr v-for="(item, key) in contextLengths" :key="key">
              <td class="ctx-key">{{ key }}</td>
              <td>
                <input
                  v-if="item._editing"
                  v-model.number="item._editValue"
                  type="number"
                  min="1"
                  class="ctx-input"
                  @keyup.enter="saveContextLength(key, item)"
                  @keyup.escape="cancelEdit(key, item)"
                />
                <span v-else class="ctx-value">{{ formatTokens(item.context_length) }}</span>
              </td>
              <td>
                <span :class="['source-tag', item.source]">
                  {{ item.source === 'config' ? '自定义' : '内置' }}
                </span>
              </td>
              <td class="ctx-actions">
                <template v-if="item._editing">
                  <button class="action-btn save" @click="saveContextLength(key, item)">保存</button>
                  <button class="action-btn cancel" @click="cancelEdit(key, item)">取消</button>
                </template>
                <template v-else>
                  <button class="action-btn edit" @click="startEdit(key, item)">编辑</button>
                  <button
                    v-if="item.source === 'config'"
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
      <button class="reload-btn" @click="loadAll">
        <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
        刷新
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '@/utils/api/index'
import { ElMessage } from 'element-plus'

const models = ref([])
const contextLengths = ref({})
const newModelKey = ref('')
const newContextLength = ref(null)

const currentDefault = computed(() => {
  return models.value.find(m => m.is_default) || {}
})

async function loadModels() {
  try {
    const resp = await api.get('/api/v1/models/')
    if (!resp.ok) return
    const data = await resp.json()
    models.value = data.models || []
  } catch (e) {
    console.error('加载模型列表失败:', e)
  }
}

async function loadContextLengths() {
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
  } catch (e) {
    console.error('加载上下文长度失败:', e)
  }
}

function loadAll() {
  loadModels()
  loadContextLengths()
}

async function switchDefault(modelId) {
  if (modelId === currentDefault.value.id) return
  try {
    const resp = await api.post('/api/v2/models/default', { model_id: modelId })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      ElMessage.error('切换失败: ' + (err.detail || resp.statusText))
      return
    }
    const data = await resp.json()
    if (data.success) {
      models.value.forEach(m => { m.is_default = m.id === modelId })
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

function startEdit(key, item) {
  item._editValue = item.context_length
  item._editing = true
}

function cancelEdit(key, item) {
  item._editValue = item.context_length
  item._editing = false
}

async function saveContextLength(key, item) {
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

.model-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px; margin-bottom: 32px;
}
.model-card {
  border: 1px solid var(--border-color); border-radius: 8px; padding: 16px;
  cursor: pointer; transition: all 0.2s; background: var(--bg-secondary);
}
.model-card:hover { border-color: var(--primary); box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.model-card.active { border-color: var(--primary); background: var(--primary-50, rgba(13, 148, 136, 0.08)); }

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
.model-card-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.tag-chip {
  padding: 2px 8px;
  background: var(--bg-tertiary, rgba(0,0,0,0.04));
  color: var(--text-tertiary);
  border-radius: 4px; font-size: 11px;
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
.context-table tr:hover { background: var(--bg-tertiary, rgba(0,0,0,0.02)); }
.ctx-key { font-family: monospace; font-size: 12px; max-width: 280px; word-break: break-all; }
.ctx-value { font-family: monospace; font-weight: 600; }

.source-tag {
  display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px;
}
.source-tag.config {
  background: var(--warning-bg, rgba(245, 158, 11, 0.1));
  color: var(--warning, #f59e0b);
}
.source-tag.builtin {
  background: var(--bg-tertiary, rgba(0,0,0,0.04));
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
.action-btn.save { background: var(--primary); color: white; border-color: var(--primary); }
.action-btn.save:hover { background: var(--primary-hover, #0f766e); }
.action-btn.delete { color: var(--danger, #ef4444); border-color: var(--danger); }
.action-btn.delete:hover { background: var(--danger); color: white; }

.add-context {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
}
.add-input { width: 200px; }

.actions { text-align: center; }
.reload-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 20px; background: var(--primary); color: white;
  border: none; border-radius: 6px; cursor: pointer; font-size: 14px;
  font-weight: 500; transition: background 0.2s;
}
.reload-btn:hover { background: var(--primary-hover, #0f766e); }
.btn-icon { width: 16px; height: 16px; }
</style>
