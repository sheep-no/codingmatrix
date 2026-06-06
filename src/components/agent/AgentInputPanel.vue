<template>
  <div class="left-panel">
    <div class="input-section">
      <div class="section-header"><h2>项目需求</h2></div>

      <textarea :value="prompt" :placeholder="placeholderText" class="prompt-textarea" rows="8" @input="$emit('update:prompt', $event.target.value)" />
      <div class="prompt-hint">Ctrl+Enter 发送 | Esc 停止</div>

      <!-- 项目名称 -->
      <div class="project-name-input">
        <label class="project-name-label">项目名称（可选）</label>
        <input
          :value="projectName"
          type="text"
          class="project-name-field"
          placeholder="留空则自动生成"
          maxlength="50"
          @input="$emit('update:projectName', $event.target.value)"
        />
      </div>

      <!-- 模型选择器 -->
      <div v-if="dynamicModels && dynamicModels.length > 0" class="model-selector">
        <label class="model-selector-label">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          使用自定义模型（可选）
        </label>
        <select :value="selectedProviderModel" class="model-select" @change="$emit('update:selectedProviderModel', $event.target.value)">
          <option value="">系统默认模型</option>
          <optgroup v-for="group in groupedDynamicModels" :key="group.provider" :label="group.provider">
            <option v-for="m in group.models" :key="m.provider_id + ':' + m.model_id" :value="m.provider_id + '::' + m.model_id">
              {{ m.model_id }}
            </option>
          </optgroup>
        </select>
      </div>

      <div v-if="!hasFiles" class="quick-templates">
        <h3>快速模板</h3>
        <div class="template-grid">
          <div class="template-item" @click="$emit('select-template', 'vue-fastapi')">
            <div class="template-icon" style="background: #42b883">文件</div>
            <div class="template-info"><div class="template-name">Vue + FastAPI</div><div class="template-desc">全栈项目</div></div>
          </div>
          <div class="template-item" @click="$emit('select-template', 'react-django')">
            <div class="template-icon" style="background: #61dafb">React</div>
            <div class="template-info"><div class="template-name">React + Django</div><div class="template-desc">全栈项目</div></div>
          </div>
          <div class="template-item" @click="$emit('select-template', 'nextjs')">
            <div class="template-icon" style="background: #000">Next</div>
            <div class="template-info"><div class="template-name">Next.js</div><div class="template-desc">全栈项目</div></div>
          </div>
          <div class="template-item" @click="$emit('select-template', 'flask')">
            <div class="template-icon" style="background: #000">Flask</div>
            <div class="template-info"><div class="template-name">Flask</div><div class="template-desc">轻量项目</div></div>
          </div>
        </div>
      </div>

      <div class="action-buttons">
        <button class="btn btn-primary" :disabled="!prompt.trim() || generating" @click="$emit('generate')">
          <span v-if="!generating">{{ hasFiles ? '继续生成' : '开始生成' }}</span>
          <span v-else>生成中...</span>
        </button>
        <button v-if="hasFiles" class="btn btn-outline btn-regenerate" @click="$emit('regenerate')">重新生成</button>
        <button v-if="hasFiles" class="btn btn-outline btn-clear" @click="$emit('clear')">清空</button>
        <button v-if="generating" class="btn btn-danger" @click="$emit('stop')">停止</button>
      </div>
    </div>

    <div v-if="hasFiles" class="files-section">
      <div class="section-header">
        <h2>项目文件</h2>
        <div class="file-stats"><span class="total-badge">总计: {{ fileCount }}</span></div>
      </div>

      <div class="file-filter-bar">
        <div class="search-box">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="search-icon">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input :value="debouncedSearchQuery" type="text" placeholder="搜索文件..." class="file-search-input" @input="onSearchInput" />
        </div>
        <select :value="filterType" class="file-filter-select" @change="$emit('update:filterType', $event.target.value)">
          <option value="all">全部类型</option>
          <option value="javascript">JavaScript</option>
          <option value="typescript">TypeScript</option>
          <option value="vue">Vue</option>
          <option value="python">Python</option>
          <option value="html">HTML</option>
          <option value="css">CSS</option>
          <option value="json">JSON</option>
        </select>
      </div>

      <!-- 虚拟滚动文件树 -->
      <div class="file-tree" @scroll="onTreeScroll">
        <div
v-for="item in flatTreeItems" :key="item.id" class="tree-item"
          :class="{ selected: selectedPath === item.path, 'is-category': item.isCategory }">
          <div v-if="item.isCategory" class="category-header" @click="$emit('toggle-category', item.categoryName)">
            <span class="category-icon">{{ item.icon }}</span>
            <span class="category-name">{{ item.name }}</span>
            <span class="category-count">({{ item.count }})</span>
            <span class="expand-icon">{{ item.expanded ? '▼' : '▶' }}</span>
          </div>
          <div v-else v-show="item.visible" class="file-item" @click="$emit('select-file', { path: item.path })">
            <span class="file-icon">{{ getFileIcon(item.path) }}</span>
            <span class="file-name">{{ getFileName(item.path) }}</span>
          </div>
        </div>
        <!-- 占位元素用于虚拟滚动 -->
        <div :style="{ height: virtualScroll.placeholderHeight + 'px' }" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  prompt: { type: String, required: true },
  placeholderText: { type: String, required: true },
  generating: { type: Boolean, required: true },
  hasFiles: { type: Boolean, required: true },
  fileCount: { type: Number, required: true },
  categories: { type: Array, required: true },
  searchQuery: { type: String, required: true },
  filterType: { type: String, required: true },
  selectedPath: { type: String, default: '' },
  dynamicModels: { type: Array, default: () => [] },
  selectedProviderModel: { type: String, default: '' },
  projectName: { type: String, default: '' }
})
const emit = defineEmits(['update:prompt', 'update:searchQuery', 'update:filterType', 'update:selectedProviderModel', 'update:projectName', 'generate', 'regenerate', 'clear', 'stop', 'select-template', 'toggle-category', 'select-file'])

const groupedDynamicModels = computed(() => {
  const groups = {}
  for (const m of (props.dynamicModels || [])) {
    if (!groups[m.provider_name]) {
      groups[m.provider_name] = { provider: m.provider_name, models: [] }
    }
    groups[m.provider_name].models.push(m)
  }
  return Object.values(groups)
})

// 虚拟滚动状态
const virtualScroll = reactive({
  scrollTop: 0,
  itemHeight: 32,
  containerHeight: 400,
  placeholderHeight: 0
})

// 扁平化文件树
const flatTreeItems = computed(() => {
  const items = []
  for (const category of props.categories) {
    const categoryFiles = category.files?.value ?? category.files ?? []
    items.push({
      id: `cat-${category.name}`,
      isCategory: true,
      categoryName: category.name,
      name: category.name,
      icon: category.icon,
      count: categoryFiles.length,
      expanded: category.expanded
    })
    if (category.expanded) {
      for (const file of categoryFiles) {
        items.push({
          id: `file-${file.path}`,
          isCategory: false,
          path: file.path,
          visible: true
        })
      }
    }
  }
  return items
})

// 监听 flatTreeItems 变化，更新占位高度
watch(flatTreeItems, (items) => {
  const totalHeight = items.length * virtualScroll.itemHeight
  virtualScroll.placeholderHeight = Math.max(0, totalHeight - items.length * virtualScroll.itemHeight)
})

// 搜索防抖
const searchDebounce = ref(null)
const debouncedSearchQuery = ref(props.searchQuery)

function onSearchInput(event) {
  const value = event.target.value
  debouncedSearchQuery.value = value
  if (searchDebounce.value) clearTimeout(searchDebounce.value)
  searchDebounce.value = setTimeout(() => {
    emit('update:searchQuery', value)
  }, 300)
}

// 快捷键支持
function handleKeydown(event) {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault()
    if (!props.prompt.trim() || props.generating) return
    emit('generate')
  }
  if (event.key === 'Escape' && props.generating) {
    event.preventDefault()
    emit('stop')
  }
}

// 虚拟滚动事件
function onTreeScroll(event) {
  virtualScroll.scrollTop = event.target.scrollTop
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  if (searchDebounce.value) clearTimeout(searchDebounce.value)
})

function getFileIcon(filePath) {
  const ext = filePath.split('.').pop().toLowerCase()
  const iconMap = { vue: '文件', jsx: 'React', tsx: 'React', js: 'JS', ts: 'TS', py: 'Python', java: 'Java', go: 'Go', html: 'HTML', css: 'CSS', json: 'JSON', md: 'MD' }
  return iconMap[ext] || '文件'
}

function getFileName(filePath) {
  return filePath.split('/').pop()
}
</script>

<style scoped>
.prompt-hint {
  font-size: 11px;
  color: var(--text-secondary);
  text-align: right;
  margin-top: 2px;
}
.project-name-input {
  margin: 8px 0 4px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.project-name-label {
  font-size: 12px;
  color: var(--text-secondary);
}
.project-name-field {
  padding: 6px 8px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 13px;
  background: var(--bg-primary);
  color: var(--text-primary);
}
.project-name-field::placeholder {
  color: var(--text-tertiary);
}
.model-selector {
  margin: 8px 0 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.model-selector-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}
.model-select {
  padding: 6px 8px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 13px;
  background: var(--bg-primary);
  cursor: pointer;
}
.model-select:hover { border-color: var(--primary); }
.model-select:focus { border-color: var(--primary); outline: none; }

/* 虚拟滚动文件树 */
.file-tree {
  overflow-y: auto;
}
.tree-item {
  height: 32px;
  display: flex;
  align-items: center;
}
.tree-item.is-category {
  font-weight: 500;
  cursor: pointer;
}
.file-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  cursor: pointer;
  width: 100%;
}
.file-item:hover {
  background: var(--bg-secondary);
}
.file-item.selected {
  background: var(--color-primary-50);
  color: var(--primary);
}
</style>
