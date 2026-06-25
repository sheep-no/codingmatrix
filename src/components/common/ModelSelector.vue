<template>
  <div class="model-selector" :class="{ 'is-open': isOpen }">
    <!-- 选择器触发器 -->
    <div class="selector-trigger" @click="toggleDropdown">
      <div class="trigger-content">
        <div v-if="selectedModel" class="selected-model">
          <span class="model-name">{{ selectedModel.name || selectedModel.id }}</span>
          <span class="model-provider">{{ selectedModel.provider_name || selectedModel.provider || '' }}</span>
        </div>
        <div v-else class="placeholder">
          {{ placeholder || '选择模型' }}
        </div>
      </div>
      <svg class="dropdown-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </div>

    <!-- 下拉面板 -->
    <Transition name="dropdown">
      <div v-if="isOpen" class="dropdown-panel" @click.stop>
        <!-- 搜索框 -->
        <div class="search-box">
          <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            ref="searchInput"
            v-model="searchQuery"
            type="text"
            placeholder="搜索模型名称、ID 或描述..."
            class="search-input"
            @keydown.escape="closeDropdown"
          />
        </div>

        <!-- 过滤器 -->
        <div v-if="showFilters" class="filter-bar">
          <button
            v-for="cap in capabilityFilters"
            :key="cap.value"
            :class="['filter-tag', { active: activeCapabilities.includes(cap.value) }]"
            @click="toggleCapability(cap.value)"
          >
            {{ cap.label }}
          </button>
        </div>

        <!-- 模型列表 -->
        <div class="model-list">
          <!-- 按供应商分组 -->
          <template v-for="group in groupedModels" :key="group.provider">
            <div class="provider-group">
              <div class="group-header">
                <span class="group-name">{{ group.provider }}</span>
                <span class="group-count">{{ group.models.length }}</span>
              </div>
              <div
                v-for="model in group.models"
                :key="model.id"
                :class="['model-item', { active: model.id === selectedId, disabled: isDisabled(model) }]"
                @click="selectModel(model)"
              >
                <div class="model-main">
                  <div class="model-info">
                    <span class="model-name">{{ model.name }}</span>
                    <span v-if="model.id" class="model-id">{{ model.id }}</span>
                  </div>
                  <div v-if="model.description" class="model-desc">{{ model.description }}</div>
                  <div class="model-meta">
                    <span v-if="model.max_context" class="meta-item context">
                      {{ formatContextLength(model.max_context) }}
                    </span>
                    <span v-if="model.cost_per_1m_input !== undefined" class="meta-item cost">
                      ¥{{ model.cost_per_1m_input }}/1M
                    </span>
                    <span v-for="tag in (model.tags || []).slice(0, 3)" :key="tag" class="meta-tag">
                      {{ tag }}
                    </span>
                  </div>
                </div>
                <div v-if="model.health_score !== undefined" class="model-health">
                  <div :class="['health-indicator', getHealthClass(model.health_score)]">
                    {{ model.health_score }}%
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- 空状态 -->
          <div v-if="filteredModels.length === 0" class="empty-state">
            <p>未找到匹配的模型</p>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  models: { type: Array, required: true },
  selectedId: { type: String, default: '' },
  placeholder: { type: String, default: '选择模型' },
  showFilters: { type: Boolean, default: true },
  disabledModels: { type: Array, default: () => [] },
  groupByProvider: { type: Boolean, default: true },
  showHealth: { type: Boolean, default: false }
})

const emit = defineEmits(['update:selectedId', 'select'])

const isOpen = ref(false)
const searchQuery = ref('')
const searchInput = ref(null)
const activeCapabilities = ref([])

const capabilityFilters = [
  { label: '文本生成', value: 'text' },
  { label: '代码生成', value: 'code' },
  { label: '推理', value: 'reasoning' },
  { label: '视觉', value: 'vision' },
  { label: '快速', value: 'fast' }
]

const selectedModel = computed(() => {
  return props.models.find(m => m.id === props.selectedId)
})

const filteredModels = computed(() => {
  let result = [...props.models]
  
  // 搜索过滤
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(m => 
      m.name?.toLowerCase().includes(query) ||
      m.id?.toLowerCase().includes(query) ||
      m.description?.toLowerCase().includes(query) ||
      m.model_key?.toLowerCase().includes(query)
    )
  }
  
  // 能力过滤
  if (activeCapabilities.value.length > 0) {
    result = result.filter(m => {
      const caps = m.capabilities || []
      return activeCapabilities.value.some(cap => caps.includes(cap))
    })
  }
  
  return result
})

const groupedModels = computed(() => {
  if (!props.groupByProvider) {
    return [{ provider: '', models: filteredModels.value }]
  }
  
  const groups = {}
  for (const model of filteredModels.value) {
    const provider = model.provider_name || model.provider || '其他'
    if (!groups[provider]) {
      groups[provider] = []
    }
    groups[provider].push(model)
  }
  
  return Object.entries(groups).map(([provider, models]) => ({
    provider,
    models
  }))
})

function isDisabled(model) {
  return props.disabledModels.includes(model.id)
}

function toggleDropdown() {
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    nextTick(() => {
      searchInput.value?.focus()
    })
  }
}

function closeDropdown() {
  isOpen.value = false
  searchQuery.value = ''
}

function selectModel(model) {
  if (isDisabled(model)) return
  emit('update:selectedId', model.id)
  emit('select', model)
  closeDropdown()
}

function toggleCapability(cap) {
  const index = activeCapabilities.value.indexOf(cap)
  if (index === -1) {
    activeCapabilities.value.push(cap)
  } else {
    activeCapabilities.value.splice(index, 1)
  }
}

function formatContextLength(tokens) {
  if (!tokens) return ''
  if (tokens >= 1024 * 1024) return `${(tokens / 1024 / 1024).toFixed(0)}M`
  if (tokens >= 1024) return `${(tokens / 1024).toFixed(0)}k`
  return `${tokens}`
}

function getHealthClass(score) {
  if (score >= 80) return 'good'
  if (score >= 50) return 'warning'
  return 'critical'
}

// 点击外部关闭
function handleClickOutside(e) {
  if (!isOpen.value) return
  const selector = e.target.closest('.model-selector')
  if (!selector) {
    closeDropdown()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.model-selector {
  position: relative;
  width: 100%;
}

.selector-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-primary);
  cursor: pointer;
  transition: all 0.2s;
}

.selector-trigger:hover {
  border-color: var(--primary);
}

.model-selector.is-open .selector-trigger {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(var(--primary-rgb), 0.1);
}

.trigger-content {
  flex: 1;
  min-width: 0;
}

.selected-model {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selected-model .model-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.selected-model .model-provider {
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 1px 6px;
  background: var(--bg-secondary);
  border-radius: 4px;
}

.placeholder {
  font-size: 14px;
  color: var(--text-tertiary);
}

.dropdown-icon {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.model-selector.is-open .dropdown-icon {
  transform: rotate(180deg);
}

/* 下拉面板 */
.dropdown-panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  max-height: 400px;
  display: flex;
  flex-direction: column;
}

.search-box {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
}

.search-icon {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  margin-right: 8px;
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 13px;
  background: transparent;
  color: var(--text-primary);
}

.search-input::placeholder {
  color: var(--text-tertiary);
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
}

.filter-tag {
  padding: 4px 10px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 12px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.filter-tag:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.filter-tag.active {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}

.model-list {
  overflow-y: auto;
  flex: 1;
  max-height: 300px;
}

.provider-group {
  padding: 4px 0;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: var(--bg-secondary);
}

.group-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.group-count {
  font-size: 11px;
  color: var(--text-tertiary);
  padding: 1px 6px;
  background: var(--bg-primary);
  border-radius: 10px;
}

.model-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.model-item:hover {
  background: var(--bg-secondary);
}

.model-item.active {
  background: var(--primary-50);
}

.model-item.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.model-main {
  flex: 1;
  min-width: 0;
}

.model-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}

.model-info .model-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.model-info .model-id {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: monospace;
}

.model-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.meta-item {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--bg-secondary);
}

.meta-item.context {
  color: var(--primary);
}

.meta-item.cost {
  color: var(--success);
}

.meta-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.model-health {
  flex-shrink: 0;
  margin-left: 8px;
}

.health-indicator {
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

.empty-state {
  text-align: center;
  padding: 24px;
  color: var(--text-tertiary);
  font-size: 13px;
}

/* 动画 */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.2s ease;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
