<template>
  <div class="dynamic-provider-manager">
    <h2 class="section-title">自定义供应商管理</h2>
    <p class="section-desc">通过 Base URL 和协议类型添加任意支持的供应商供应商，系统自动拉取模型列表</p>
    
    <!-- 添加供应商表单 -->
    <div class="add-provider-form">
      <h3 class="form-title">添加供应商</h3>
      <div class="form-grid">
        <div class="form-group">
          <label>供应商名称</label>
          <input v-model="form.name" type="text" placeholder="例如：Claude 代理" class="form-input" />
        </div>
        <div class="form-group">
          <label>Base URL</label>
          <input v-model="form.base_url" type="text" placeholder="https://api.example.com/v1" class="form-input" />
        </div>
        <div class="form-group">
          <label>协议类型</label>
          <select v-model="form.protocol" class="form-select">
            <option value="openai">OpenAI 兼容</option>
            <option value="anthropic">Anthropic 原生</option>
          </select>
        </div>
        <div class="form-group">
          <label>API Key</label>
          <input v-model="form.api_key" type="password" placeholder="输入 API Key" class="form-input" />
        </div>
      </div>
      <button
        :disabled="loading || !form.name || !form.base_url || !form.api_key"
        class="submit-btn"
        @click="submitForm"
      >
        {{ loading ? '添加中...' : '添加供应商' }}
      </button>
    </div>

    <!-- 供应商列表 -->
    <div v-if="providers.length > 0" class="provider-list">
      <h3 class="list-title">已添加的供应商 ({{ providers.length }})</h3>
      
      <div v-for="p in providers" :key="p.id" class="provider-card">
        <div class="provider-header">
          <div class="provider-info">
            <span class="provider-name">{{ p.name }}</span>
            <span class="provider-url">{{ p.base_url }}</span>
          </div>
          <div class="provider-meta">
            <span :class="['protocol-badge', p.protocol]">{{ p.protocol }}</span>
            <span :class="['status-badge', p.enabled ? 'enabled' : 'disabled']">
              {{ p.enabled ? '已启用' : '已禁用' }}
            </span>
          </div>
        </div>

        <!-- 模型列表 -->
        <div class="models-section">
          <div class="models-header">
            <span class="models-title">模型列表 ({{ (p.models || []).length }})</span>
            <div class="models-actions">
              <button class="btn-sm sync-btn" :disabled="loading" @click="syncModelsAction(p.id)">
                {{ loading ? '同步中...' : '同步模型' }}
              </button>
              <button class="btn-sm test-btn" :disabled="loading" @click="testProviderAction(p.id)">
                {{ loading ? '测试中...' : '测试连接' }}
              </button>
            </div>
          </div>
          
          <div v-if="p.sync_error" class="sync-error">
            {{ p.sync_error }}
          </div>
          
          <div v-if="p.last_sync > 0" class="sync-info">
            最后同步：{{ formatTime(p.last_sync) }}
          </div>

          <div v-if="(p.models || []).length > 0" class="model-tags">
            <span v-for="m in (p.models || []).slice(0, 20)" :key="m.id || m" class="model-tag">
              {{ typeof m === 'string' ? m : m.id }}
            </span>
            <span v-if="(p.models || []).length > 20" class="more-tag">
              +{{ (p.models || []).length - 20 }}
            </span>
          </div>
          <div v-else class="empty-models">
            点击“同步模型”拉取模型列表
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="provider-actions">
          <button class="action-btn toggle-btn" @click="toggleProviderAction(p.id)">
            {{ p.enabled ? '禁用' : '启用' }}
          </button>
          <button class="action-btn delete-btn" @click="deleteProviderAction(p.id)">
            删除
          </button>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <p>暂无自定义供应商</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useProviderStore } from '@/stores/providers'
import { ElMessage, ElMessageBox } from 'element-plus'

const store = useProviderStore()
const loading = ref(false)
const providers = computed(() => store.providers)

const form = reactive({
  name: '',
  base_url: '',
  protocol: 'openai',
  api_key: '',
})

onMounted(() => {
  store.loadFromStorage()
  store.listProviders().catch(() => {})
})

async function submitForm() {
  if (!form.name || !form.base_url || !form.api_key) {
    ElMessage.warning('请填写所有必填字段')
    return
  }
  loading.value = true
  try {
    await store.addProvider({
      name: form.name,
      base_url: form.base_url,
      protocol: form.protocol,
      api_key: form.api_key,
    })
    ElMessage.success(`供应商 "${form.name}" 已添加`)
    form.name = ''
    form.base_url = ''
    form.api_key = ''
    form.protocol = 'openai'
  } catch (e) {
    ElMessage.error('添加失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function deleteProviderAction(id) {
  const p = store.providers.find(x => x.id === id)
  try {
    await ElMessageBox.confirm(`确定要删除供应商 "${p?.name}" 吗？`, '确认删除', { type: 'warning' })
    await store.deleteProvider(id)
    ElMessage.success('供应商已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败：' + (e.message || '未知错误'))
  }
}

async function toggleProviderAction(id) {
  try {
    await store.toggleProvider(id)
    const p = store.providers.find(x => x.id === id)
    ElMessage.success(`供应商已${p?.enabled ? '启用' : '禁用'}`)
  } catch (e) {
    ElMessage.error('操作失败：' + (e.message || '未知错误'))
  }
}

async function syncModelsAction(id) {
  loading.value = true
  try {
    const result = await store.syncModels(id, true)
    if (result.error) {
      ElMessage.warning('同步失败：' + result.error)
    } else {
      ElMessage.success(`同步完成，共 ${result.count} 个模型`)
    }
  } catch (e) {
    ElMessage.error('同步失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function testProviderAction(id) {
  loading.value = true
  try {
    const result = await store.testProvider(id)
    if (result.success) {
      ElMessage.success('连接测试成功：' + result.message)
    } else {
      ElMessage.warning('连接测试失败：' + result.message)
    }
  } catch (e) {
    ElMessage.error('测试失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function formatTime(ts) {
  if (!ts) return '从未'
  const d = new Date(ts * 1000)
  const now = new Date()
  const diff = Math.floor((now - d) / 1000)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
}
</script>

<style scoped>
.dynamic-provider-manager {
  padding: 20px;
  max-width: 1000px;
  margin: 0 auto;
}

.section-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 8px;
}

.section-desc {
  font-size: 14px;
  color: #909399;
  margin-bottom: 24px;
}

.add-provider-form {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;
}

.form-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
}

.form-input,
.form-select {
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 14px;
  color: #333;
  background: #fff;
  width: 100%;
}

.form-input:focus,
.form-select:focus {
  border-color: #409eff;
  outline: none;
}

.submit-btn {
  padding: 10px 24px;
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.submit-btn:disabled {
  background: #a0cfff;
  cursor: not-allowed;
}

.list-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
}

.provider-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.provider-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 20px;
  background: #fff;
}

.provider-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.provider-name {
  font-size: 16px;
  font-weight: 600;
  display: block;
}

.provider-url {
  font-size: 13px;
  color: #909399;
  display: block;
  margin-top: 4px;
}

.provider-meta {
  display: flex;
  gap: 8px;
  align-items: center;
}

.protocol-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.protocol-badge.openai {
  background: #e1f3d8;
  color: #67c23a;
}

.protocol-badge.anthropic {
  background: #f0e6ff;
  color: #9b59b6;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.status-badge.enabled {
  background: #e1f3d8;
  color: #67c23a;
}

.status-badge.disabled {
  background: #f4f4f5;
  color: #909399;
}

.models-section {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 16px;
}

.models-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.models-title {
  font-size: 14px;
  font-weight: 500;
}

.models-actions {
  display: flex;
  gap: 8px;
}

.btn-sm {
  padding: 4px 12px;
  font-size: 13px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  cursor: pointer;
  background: #fff;
}

.btn-sm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sync-btn {
  color: #409eff;
  border-color: #d9ecff;
}

.sync-btn:hover {
  background: #d9ecff;
}

.test-btn {
  color: #67c23a;
  border-color: #e1f3d8;
}

.test-btn:hover {
  background: #e1f3d8;
}

.sync-error {
  padding: 8px 12px;
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  border-radius: 4px;
  color: #f56c6c;
  font-size: 13px;
  margin-bottom: 8px;
}

.sync-info {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.model-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.model-tag {
  padding: 4px 10px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}

.more-tag {
  padding: 4px 10px;
  background: #f0f9ff;
  border-radius: 4px;
  font-size: 12px;
  color: #409eff;
}

.empty-models {
  text-align: center;
  color: #909399;
  font-size: 13px;
  padding: 16px;
}

.provider-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.toggle-btn {
  background: #d9ecff;
  color: #409eff;
}

.delete-btn {
  background: #fde2e2;
  color: #f56c6c;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #909399;
  background: #f5f7fa;
  border-radius: 8px;
}
</style>
