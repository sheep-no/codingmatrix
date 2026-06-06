<template>
  <div class="agent-model-config">
    <h3 class="section-title">Agent 模型配置</h3>
    <p class="section-desc">
      {{ isSuperUser ? '配置 Agent 各环节使用的模型、降级链和错误恢复策略。修改后立即生效。' : '查看 Agent 各环节使用的模型配置。如需修改，请联系超级管理员。' }}
    </p>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <span class="loading-spinner"></span> 加载中...
    </div>

    <template v-else>
      <!-- 模型分配表 -->
      <div class="config-table-wrapper">
        <table class="config-table">
          <thead>
            <tr>
              <th>复杂度</th>
              <th>架构师</th>
              <th>前端工程师</th>
              <th>后端工程师</th>
              <th>审查员</th>
              <th>兜底模型</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="complexity in complexityLevels" :key="complexity">
              <td class="complexity-cell">
                <span class="complexity-badge" :class="complexity.toLowerCase()">{{ complexity }}</span>
              </td>
              <td v-for="role in roles" :key="role">
                <select
                  v-if="isSuperUser"
                  :value="getSelectedModel(complexity, role)"
                  class="model-select"
                  @change="updateModel(complexity, role, $event.target.value)"
                >
                  <option v-for="model in availableModels" :key="model.id" :value="model.id">
                    {{ model.name }}
                  </option>
                </select>
                <span v-else class="model-readonly">
                  {{ getModelName(getSelectedModel(complexity, role)) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 超级管理员专属：降级链配置 -->
      <template v-if="isSuperUser">
        <h3 class="section-title" style="margin-top: 32px;">降级链配置</h3>
        <p class="section-desc">配置模型降级顺序。当首选模型不可用时，按顺序尝试下一个模型。</p>

        <div class="fallback-chains">
          <div v-for="(chainModels, chainName) in configData.fallback_chains" :key="chainName" class="chain-card">
            <div class="chain-header">
              <span class="chain-name">{{ chainName }}</span>
              <button class="chain-save-btn" :disabled="chainSaving" @click="saveChain(chainName, chainModels)">
                {{ chainSaving ? '保存中...' : '保存' }}
              </button>
            </div>
            <div class="chain-models">
              <div
                v-for="(modelId, idx) in chainModels"
                :key="idx"
                class="chain-model-item"
              >
                <span class="chain-index">{{ idx + 1 }}</span>
                <select
                  :value="modelId"
                  class="model-select"
                  @change="updateChainModel(chainName, idx, $event.target.value)"
                >
                  <option v-for="model in availableModels" :key="model.id" :value="model.id">
                    {{ model.name }}
                  </option>
                </select>
                <button class="chain-remove-btn" title="移除" @click="removeChainModel(chainName, idx)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
              <button class="chain-add-btn" @click="addChainModel(chainName)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                添加模型
              </button>
            </div>
          </div>
        </div>
      </template>

      <!-- 超级管理员专属：错误类型模型映射 -->
      <template v-if="isSuperUser">
        <h3 class="section-title" style="margin-top: 32px;">错误类型模型映射</h3>
        <p class="section-desc">配置不同错误类型使用的修复模型。</p>

        <div class="error-type-grid">
          <div v-for="(modelId, errorType) in configData.error_type_models" :key="errorType" class="error-type-item">
            <span class="error-type-name">{{ errorType }}</span>
            <select
              :value="modelId"
              class="model-select"
              @change="updateErrorTypeModel(errorType, $event.target.value)"
            >
              <option v-for="model in availableModels" :key="model.id" :value="model.id">
                {{ model.name }}
              </option>
            </select>
          </div>
        </div>
      </template>

      <!-- 配置信息 -->
      <div class="config-info">
        <div class="info-item">
          <span class="info-label">配置文件：</span>
          <span class="info-value">data/agent_model_config.json</span>
        </div>
        <div class="info-item">
          <span class="info-label">最后更新：</span>
          <span class="info-value">{{ configData.last_updated || '未配置' }}</span>
        </div>
      </div>

      <!-- 超级管理员专属：操作按钮 -->
      <div v-if="isSuperUser" class="config-actions">
        <button class="reload-btn" :disabled="reloading" @click="reloadConfig">
          <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
          {{ reloading ? '重新加载中...' : '重新加载配置' }}
        </button>
        <span class="save-hint">修改后自动保存并生效</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useUserStore } from '@/stores/user'
import { api } from '@/utils/api/index'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()
const isSuperUser = computed(() => userStore.isSuperUser)

const loading = ref(false)
const reloading = ref(false)
const chainSaving = ref(false)
const availableModels = ref([])

const complexityLevels = ['SIMPLE', 'SMALL', 'MEDIUM', 'LARGE', 'ENTERPRISE']
const roles = ['architect', 'frontend', 'backend', 'reviewer', 'fallback']

const configData = ref({
  version: '1.0',
  description: 'Agent 模型配置',
  last_updated: '',
  assignments: {},
  fallback_chains: {},
  error_type_models: {},
  settings: {}
})

function getModelName(modelId) {
  const m = availableModels.value.find(m => m.id === modelId)
  return m ? m.name : modelId
}

async function loadModels() {
  try {
    const resp = await api.get('/api/v1/models/')
    if (resp.ok) {
      const data = await resp.json()
      availableModels.value = data.models || []
    }
  } catch {
    ElMessage.error('加载模型列表失败')
  }
}

async function loadConfig() {
  loading.value = true
  try {
    const resp = await api.get('/api/v1/models/agent-config')
    if (resp.ok) {
      const data = await resp.json()
      configData.value = { ...configData.value, ...data }
    }
  } catch {
    ElMessage.error('加载配置失败')
  } finally {
    loading.value = false
  }
}

function getSelectedModel(complexity, role) {
  const assignment = configData.value.assignments?.[complexity]
  if (!assignment) {
    const defaults = {
      SIMPLE: { architect: 'qwen3.5-4b', frontend: 'qwen3-8b', backend: 'qwen3-8b', reviewer: 'qwen3-8b', fallback: 'qwen3.5-4b' },
      SMALL: { architect: 'glm-z1-9b', frontend: 'qwen3-8b', backend: 'deepseek-r1', reviewer: 'glm-z1-9b', fallback: 'qwen3-8b' },
      MEDIUM: { architect: 'glm-z1-9b', frontend: 'qwen3-8b', backend: 'deepseek-r1', reviewer: 'deepseek-r1', fallback: 'qwen3-8b' },
      LARGE: { architect: 'glm-z1-9b', frontend: 'qwen3-8b', backend: 'deepseek-r1', reviewer: 'deepseek-r1', fallback: 'qwen3-8b' },
      ENTERPRISE: { architect: 'glm-z1-9b', frontend: 'qwen3-8b', backend: 'deepseek-r1', reviewer: 'deepseek-r1', fallback: 'qwen3-8b' },
    }
    return defaults[complexity]?.[role] || 'qwen3-8b'
  }
  const roleKey = `${role}_model`
  return assignment[roleKey] || 'qwen3-8b'
}

async function updateModel(complexity, role, modelId) {
  try {
    const resp = await api.put('/api/v2/models/agent-config', {
      complexity,
      role,
      model_id: modelId
    })
    if (resp.ok) {
      const data = await resp.json()
      if (data.success) {
        if (!configData.value.assignments[complexity]) {
          configData.value.assignments[complexity] = {}
        }
        const roleKey = `${role}_model`
        configData.value.assignments[complexity][roleKey] = modelId
        if (data.config?.last_updated) {
          configData.value.last_updated = data.config.last_updated
        }
        ElMessage.success(`已更新 ${complexity} 的 ${role} 为 ${getModelName(modelId)}`)
      }
    } else {
      const err = await resp.json().catch(() => ({}))
      ElMessage.error('更新失败: ' + (err.detail || resp.statusText))
    }
  } catch (e) {
    ElMessage.error('更新失败: ' + e.message)
  }
}

function updateChainModel(chainName, idx, modelId) {
  if (configData.value.fallback_chains?.[chainName]) {
    configData.value.fallback_chains[chainName][idx] = modelId
  }
}

function addChainModel(chainName) {
  if (configData.value.fallback_chains?.[chainName]) {
    configData.value.fallback_chains[chainName].push('qwen3-8b')
  }
}

function removeChainModel(chainName, idx) {
  if (configData.value.fallback_chains?.[chainName]) {
    configData.value.fallback_chains[chainName].splice(idx, 1)
  }
}

async function saveChain(chainName, models) {
  chainSaving.value = true
  try {
    const resp = await api.put('/api/v2/models/agent-config/fallback-chain', {
      chain_name: chainName,
      models
    })
    if (resp.ok) {
      const data = await resp.json()
      if (data.success) {
        if (data.config?.last_updated) {
          configData.value.last_updated = data.config.last_updated
        }
        ElMessage.success(`降级链「${chainName}」已保存`)
      }
    } else {
      const err = await resp.json().catch(() => ({}))
      ElMessage.error('保存失败: ' + (err.detail || resp.statusText))
    }
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  } finally {
    chainSaving.value = false
  }
}

async function updateErrorTypeModel(errorType, modelId) {
  try {
    const resp = await api.put('/api/v2/models/agent-config/error-type-model', {
      error_type: errorType,
      model_id: modelId
    })
    if (resp.ok) {
      const data = await resp.json()
      if (data.success) {
        if (!configData.value.error_type_models) {
          configData.value.error_type_models = {}
        }
        configData.value.error_type_models[errorType] = modelId
        if (data.config?.last_updated) {
          configData.value.last_updated = data.config.last_updated
        }
        ElMessage.success(`已更新错误类型「${errorType}」的模型为 ${getModelName(modelId)}`)
      }
    } else {
      const err = await resp.json().catch(() => ({}))
      ElMessage.error('更新失败: ' + (err.detail || resp.statusText))
    }
  } catch (e) {
    ElMessage.error('更新失败: ' + e.message)
  }
}

async function reloadConfig() {
  reloading.value = true
  try {
    const resp = await api.post('/api/v2/models/agent-config/reload')
    if (resp.ok) {
      const data = await resp.json()
      if (data.success) {
        configData.value = { ...configData.value, ...(data.config || {}) }
        ElMessage.success('配置已重新加载')
      }
    } else {
      const err = await resp.json().catch(() => ({}))
      ElMessage.error('重新加载失败: ' + (err.detail || resp.statusText))
    }
  } catch (e) {
    ElMessage.error('重新加载失败: ' + e.message)
  } finally {
    reloading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadModels(), loadConfig()])
})
</script>

<style scoped>
.agent-model-config { padding: 20px; max-width: 1000px; margin: 0 auto; }
.section-title { font-size: 18px; margin-bottom: 8px; color: var(--text-primary); }
.section-desc { font-size: 14px; color: var(--text-tertiary); margin-bottom: 24px; }

.loading-state {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 48px; color: var(--text-tertiary); font-size: 14px;
}
.loading-spinner {
  width: 16px; height: 16px; border: 2px solid var(--border-color);
  border-top-color: var(--primary); border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.config-table-wrapper { overflow-x: auto; margin-bottom: 24px; }
.config-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.config-table th, .config-table td { padding: 12px 16px; border: 1px solid var(--border-color); text-align: center; }
.config-table th { background: var(--bg-secondary); font-weight: 600; white-space: nowrap; color: var(--text-secondary); }
.config-table td { background: var(--bg-primary); }

.complexity-cell { text-align: left; }
.complexity-badge { display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.complexity-badge.simple { background: var(--success-bg); color: var(--success); }
.complexity-badge.small { background: var(--primary-50); color: var(--primary); }
.complexity-badge.medium { background: var(--warning-bg); color: var(--warning); }
.complexity-badge.large { background: var(--danger-bg); color: var(--danger); }
.complexity-badge.enterprise { background: var(--color-primary-50); color: var(--color-primary-700); }

.model-select { width: 100%; padding: 6px 8px; border: 1px solid var(--border-color); border-radius: 4px; font-size: 13px; background: var(--bg-primary); color: var(--text-primary); cursor: pointer; }
.model-select:hover { border-color: var(--primary); }
.model-select:focus { border-color: var(--primary); outline: none; }

.model-readonly { font-size: 13px; color: var(--text-secondary); }

/* 降级链 */
.fallback-chains { display: flex; flex-direction: column; gap: 16px; margin-bottom: 24px; }
.chain-card { border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; background: var(--bg-secondary); }
.chain-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.chain-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.chain-save-btn { padding: 4px 16px; background: var(--primary); color: var(--bg-primary, #fff); border: none; border-radius: 4px; font-size: 13px; cursor: pointer; }
.chain-save-btn:hover:not(:disabled) { background: var(--primary-hover); }
.chain-save-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.chain-models { display: flex; flex-direction: column; gap: 8px; }
.chain-model-item { display: flex; align-items: center; gap: 8px; }
.chain-index { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 50%; background: var(--primary); color: var(--bg-primary, #fff); font-size: 12px; font-weight: 600; flex-shrink: 0; }
.chain-remove-btn { background: none; border: none; cursor: pointer; color: var(--text-tertiary); padding: 4px; display: flex; align-items: center; }
.chain-remove-btn:hover { color: var(--danger); }
.chain-add-btn { display: flex; align-items: center; gap: 4px; padding: 6px 12px; background: var(--primary-50); color: var(--primary); border: 1px dashed var(--primary-200); border-radius: 4px; font-size: 13px; cursor: pointer; margin-top: 4px; }
.chain-add-btn:hover { background: var(--primary-100); }

/* 错误类型映射 */
.error-type-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; margin-bottom: 24px; }
.error-type-item { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--bg-secondary); }
.error-type-name { font-size: 13px; font-weight: 600; color: var(--text-primary); min-width: 100px; }

.config-info { display: flex; gap: 32px; margin-bottom: 24px; padding: 16px; background: var(--bg-secondary); border-radius: 8px; }
.info-item { display: flex; gap: 8px; }
.info-label { font-size: 13px; color: var(--text-tertiary); }
.info-value { font-size: 13px; color: var(--text-secondary); }

.config-actions { display: flex; justify-content: center; align-items: center; gap: 16px; padding: 16px; background: var(--bg-secondary); border-radius: 8px; }
.reload-btn { display: flex; align-items: center; gap: 8px; padding: 8px 20px; background: var(--primary); color: var(--bg-primary, #fff); border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
.reload-btn:hover:not(:disabled) { background: var(--primary-hover); }
.reload-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-icon { width: 16px; height: 16px; }
.save-hint { font-size: 13px; color: var(--text-tertiary); }
</style>
