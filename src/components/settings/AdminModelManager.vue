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

    <!-- 刷新按钮 -->
    <div class="actions">
      <button class="reload-btn" @click="loadModels">
        <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
        刷新模型列表
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/utils/api/base'
import { ElMessage } from 'element-plus'

const models = ref([])

const currentDefault = computed(() => {
  return models.value.find(m => m.is_default) || {}
})

async function loadModels() {
  try {
    const resp = await api.get('/api/v1/models/')
    models.value = resp.data.models || []
  } catch (e) {
    console.error('加载模型列表失败:', e)
  }
}

async function switchDefault(modelId) {
  if (modelId === currentDefault.value.id) return
  try {
    const resp = await api.post('/api/v2/models/default', { model_id: modelId })
    if (resp.data.success) {
      models.value.forEach(m => { m.is_default = m.id === modelId })
      ElMessage.success(`默认模型已切换为 ${resp.data.new_default}`)
    }
  } catch (e) {
    ElMessage.error('切换失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(loadModels)
</script>

<style scoped>
.admin-model-manager { padding: 20px; max-width: 1000px; margin: 0 auto; }
.section-title { font-size: 18px; margin-bottom: 8px; }
.section-desc { font-size: 14px; color: #606266; margin-bottom: 24px; }

.current-default {
  display: flex; align-items: center; gap: 16px;
  padding: 16px 20px; background: #ecf5ff; border: 1px solid #d9ecff;
  border-radius: 8px; margin-bottom: 24px;
}
.default-label { font-size: 14px; color: #409eff; font-weight: 600; white-space: nowrap; }
.default-value { display: flex; flex-direction: column; }
.model-name { font-size: 16px; font-weight: 600; color: #303133; }
.model-desc { font-size: 13px; color: #606266; }

.model-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px; margin-bottom: 24px;
}
.model-card {
  border: 2px solid #e4e7ed; border-radius: 8px; padding: 16px;
  cursor: pointer; transition: all 0.2s; background: #fff;
}
.model-card:hover { border-color: #c0c4cc; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.model-card.active { border-color: #409eff; background: #f0f7ff; }

.model-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.model-card-name { font-size: 15px; font-weight: 600; color: #303133; }
.default-badge {
  padding: 2px 8px; background: #409eff; color: #fff;
  border-radius: 4px; font-size: 11px; font-weight: 600;
}
.model-card-id { font-size: 12px; color: #909399; margin-bottom: 8px; font-family: monospace; }
.model-card-desc { font-size: 13px; color: #606266; margin-bottom: 12px; }
.model-card-caps { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.cap-tag {
  padding: 2px 8px; background: #e1f3d8; color: #67c23a;
  border-radius: 4px; font-size: 11px;
}
.model-card-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.tag-chip {
  padding: 2px 8px; background: #f4f4f5; color: #909399;
  border-radius: 4px; font-size: 11px;
}

.actions { text-align: center; }
.reload-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 20px; background: #409eff; color: #fff;
  border: none; border-radius: 4px; cursor: pointer; font-size: 14px;
}
.reload-btn:hover { background: #66b1ff; }
.btn-icon { width: 16px; height: 16px; }
</style>
